"""Persistent scheduler for Akira.

The scheduler decides when a job is due. Actual execution is delegated to the
normal event/task pipeline.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = ROOT / "runtime"
SCHEDULE_FILE = RUNTIME_DIR / "scheduled_jobs.json"
MAX_JOBS = 200


def _now():
    return datetime.now().astimezone()


def _parse_time(value):
    if not value:
        return None
    value = str(value).strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    result = datetime.fromisoformat(value)
    return result.astimezone() if result.tzinfo is None else result


def _iso(value):
    return None if value is None else value.astimezone().isoformat(timespec="seconds")


class Scheduler:
    def __init__(self):
        self._lock = threading.RLock()
        self._jobs = {}
        self._load()

    def _load(self):
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        if not SCHEDULE_FILE.exists():
            return
        try:
            payload = json.loads(SCHEDULE_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(payload, list):
            for job in payload[-MAX_JOBS:]:
                if isinstance(job, dict) and job.get("id"):
                    self._jobs[job["id"]] = job

    def _save(self):
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_path = tempfile.mkstemp(
            prefix=".scheduled_jobs-", suffix=".tmp", dir=RUNTIME_DIR
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump(list(self._jobs.values())[-MAX_JOBS:], file, ensure_ascii=False, indent=2)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary_path, SCHEDULE_FILE)
        except Exception:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass
            raise

    def create(self, goal, run_at=None, interval_seconds=None):
        goal = str(goal or "").strip()
        if not goal:
            return {"success": False, "error": "empty_goal", "output": "Нельзя создать пустую scheduled task."}
        if run_at is None:
            return {"success": False, "error": "missing_run_at", "output": "Не указано время запуска."}
        try:
            first_run = _parse_time(run_at)
        except (TypeError, ValueError) as error:
            return {"success": False, "error": "invalid_run_at", "output": "Некорректный ISO-8601 timestamp: " + str(error)}
        if first_run is None:
            return {"success": False, "error": "invalid_run_at", "output": "Некорректное время запуска."}

        if isinstance(interval_seconds, bool):
            return {"success": False, "error": "invalid_interval", "output": "interval_seconds должен быть целым числом."}
        try:
            interval = int(interval_seconds) if interval_seconds is not None else None
        except (TypeError, ValueError):
            return {"success": False, "error": "invalid_interval", "output": "interval_seconds должен быть числом."}
        if interval is not None and interval <= 0:
            return {"success": False, "error": "invalid_interval", "output": "interval_seconds должен быть > 0."}

        now = _now()
        job = {
            "id": uuid.uuid4().hex[:12], "goal": goal,
            "kind": "interval" if interval is not None else "once",
            "run_at": _iso(first_run), "next_run": _iso(first_run),
            "interval_seconds": interval, "enabled": True, "created_at": _iso(now),
            "last_run": None, "run_count": 0, "last_task_id": None, "last_error": None,
        }
        with self._lock:
            self._jobs[job["id"]] = job
            self._save()
        return {"success": True, "job_id": job["id"], "job": dict(job), "output": f"Scheduled task {job['id']} создан."}

    def cancel(self, job_id):
        with self._lock:
            job = self._jobs.get(str(job_id or ""))
            if job is None:
                return {"success": False, "error": "job_not_found", "output": f"Scheduled task {job_id} не найден."}
            job["enabled"] = False
            job["cancelled_at"] = _iso(_now())
            self._save()
        return {"success": True, "job_id": job_id, "output": f"Scheduled task {job_id} отключён."}

    def list_jobs(self, limit=50):
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 50
        limit = max(1, min(limit, 100))
        with self._lock:
            jobs = [dict(job) for job in list(self._jobs.values())[-limit:]]
        jobs.reverse()
        return {"success": True, "jobs": jobs, "output": json.dumps(jobs, ensure_ascii=False, indent=2)}

    def tick(self):
        now = _now()
        due = []
        with self._lock:
            for job in self._jobs.values():
                if not job.get("enabled"):
                    continue
                try:
                    next_run = _parse_time(job.get("next_run"))
                except (TypeError, ValueError):
                    job["enabled"] = False
                    job["last_error"] = "invalid_next_run"
                    continue
                if next_run is not None and next_run <= now:
                    due.append(job["id"])

            launch_payloads = []
            for job_id in due:
                current = self._jobs.get(job_id)
                if current is None:
                    continue
                current["last_run"] = _iso(now)
                current["run_count"] = int(current.get("run_count") or 0) + 1
                if current.get("kind") == "interval":
                    interval = int(current.get("interval_seconds") or 0)
                    next_run = _parse_time(current.get("next_run")) or now
                    while next_run <= now:
                        next_run += timedelta(seconds=interval)
                    current["next_run"] = _iso(next_run)
                else:
                    current["enabled"] = False
                    current["next_run"] = None
                launch_payloads.append(dict(current))
            self._save()

        if not launch_payloads:
            return {"success": True, "launched": [], "output": "Scheduler: no jobs due."}

        from event_bus import emit_event
        launched = []
        for job in launch_payloads:
            try:
                result = emit_event("schedule.due", {
                    "job_id": job["id"], "goal": job["goal"], "kind": job.get("kind"),
                    "scheduled_for": job.get("last_run"),
                }, source="scheduler")
            except Exception as error:
                result = {"success": False, "error": str(error), "launched": []}
            spawn = result.get("launched") or []
            with self._lock:
                current = self._jobs.get(job["id"])
                if current is not None:
                    if spawn:
                        current["last_task_id"] = spawn[0].get("task_id")
                        current["last_error"] = None
                        launched.extend(spawn)
                    elif not result.get("success"):
                        current["last_error"] = result.get("error") or result.get("output")
                    self._save()
        return {"success": True, "launched": launched, "output": json.dumps(launched, ensure_ascii=False)}


_scheduler = None
_scheduler_lock = threading.Lock()


def get_scheduler():
    global _scheduler
    if _scheduler is None:
        with _scheduler_lock:
            if _scheduler is None:
                _scheduler = Scheduler()
    return _scheduler


def schedule_task(goal, run_at, interval_seconds=None):
    return get_scheduler().create(goal, run_at, interval_seconds)


def scheduled_tasks(limit=50):
    return get_scheduler().list_jobs(limit)


def scheduled_task_cancel(job_id):
    return get_scheduler().cancel(job_id)
