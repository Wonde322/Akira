
"""Persistent scheduler for Akira.

The scheduler only decides WHEN a task should start.
Actual execution is delegated to TaskRuntime -> Brain.

Supported jobs:

    once
        Run once at a specific ISO-8601 timestamp.

    interval
        Run repeatedly every N seconds.

Persistence:

    runtime/scheduled_jobs.json

The daemon calls scheduler.tick() from its heartbeat.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parent

RUNTIME_DIR = ROOT / "runtime"

SCHEDULE_FILE = (
    RUNTIME_DIR
    / "scheduled_jobs.json"
)

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

    if result.tzinfo is None:
        result = result.astimezone()

    return result


def _iso(value):
    if value is None:
        return None

    return value.astimezone().isoformat(
        timespec="seconds"
    )


class Scheduler:
    """Persistent time-based task scheduler."""

    def __init__(self):
        self._lock = threading.RLock()
        self._jobs = {}

        self._load()

    # ========================================================
    # Persistence
    # ========================================================

    def _load(self):
        RUNTIME_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        if not SCHEDULE_FILE.exists():
            return

        try:
            payload = json.loads(
                SCHEDULE_FILE.read_text(
                    encoding="utf-8",
                )
            )
        except Exception:
            return

        if not isinstance(payload, list):
            return

        for job in payload[-MAX_JOBS:]:
            if not isinstance(job, dict):
                continue

            job_id = job.get("id")

            if job_id:
                self._jobs[job_id] = job

    def _save(self):
        RUNTIME_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        data = list(
            self._jobs.values()
        )[-MAX_JOBS:]

        temporary = SCHEDULE_FILE.with_suffix(
            ".json.tmp"
        )

        temporary.write_text(
            json.dumps(
                data,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        temporary.replace(
            SCHEDULE_FILE
        )

    # ========================================================
    # Create
    # ========================================================

    def create(
        self,
        goal,
        run_at=None,
        interval_seconds=None,
    ):
        goal = str(goal or "").strip()

        if not goal:
            return {
                "success": False,
                "error": "empty_goal",
                "output": "Нельзя создать пустую scheduled task.",
            }

        if run_at is None:
            return {
                "success": False,
                "error": "missing_run_at",
                "output": "Не указано время запуска.",
            }

        try:
            first_run = _parse_time(run_at)
        except Exception as error:
            return {
                "success": False,
                "error": "invalid_run_at",
                "output": (
                    "Некорректный ISO-8601 timestamp: "
                    + str(error)
                ),
            }

        if first_run is None:
            return {
                "success": False,
                "error": "invalid_run_at",
                "output": "Некорректное время запуска.",
            }

        try:
            interval = (
                int(interval_seconds)
                if interval_seconds is not None
                else None
            )
        except Exception:
            return {
                "success": False,
                "error": "invalid_interval",
                "output": "interval_seconds должен быть числом.",
            }

        if interval is not None and interval <= 0:
            return {
                "success": False,
                "error": "invalid_interval",
                "output": "interval_seconds должен быть > 0.",
            }

        kind = (
            "interval"
            if interval is not None
            else "once"
        )

        job_id = uuid.uuid4().hex[:12]

        now = _now()

        job = {
            "id": job_id,
            "goal": goal,
            "kind": kind,
            "run_at": _iso(first_run),
            "next_run": _iso(first_run),
            "interval_seconds": interval,
            "enabled": True,
            "created_at": _iso(now),
            "last_run": None,
            "run_count": 0,
            "last_task_id": None,
            "last_error": None,
        }

        with self._lock:
            self._jobs[job_id] = job
            self._save()

        return {
            "success": True,
            "job_id": job_id,
            "job": dict(job),
            "output": (
                f"Scheduled task {job_id} создан."
            ),
        }

    # ========================================================
    # Cancel
    # ========================================================

    def cancel(self, job_id):
        job_id = str(job_id or "")

        with self._lock:
            job = self._jobs.get(job_id)

            if job is None:
                return {
                    "success": False,
                    "error": "job_not_found",
                    "output": (
                        f"Scheduled task {job_id} не найден."
                    ),
                }

            job["enabled"] = False
            job["cancelled_at"] = _iso(
                _now()
            )

            self._save()

        return {
            "success": True,
            "job_id": job_id,
            "output": (
                f"Scheduled task {job_id} отключён."
            ),
        }

    # ========================================================
    # List
    # ========================================================

    def list_jobs(self, limit=50):
        try:
            limit = int(limit)
        except Exception:
            limit = 50

        limit = max(
            1,
            min(limit, 100),
        )

        with self._lock:
            jobs = list(
                self._jobs.values()
            )[-limit:]

            jobs.reverse()

        return {
            "success": True,
            "jobs": jobs,
            "output": json.dumps(
                jobs,
                ensure_ascii=False,
                indent=2,
            ),
        }

    # ========================================================
    # Tick
    # ========================================================

    def tick(self):
        """Launch all jobs whose next_run has arrived."""

        now = _now()
        due = []

        with self._lock:
            for job in self._jobs.values():

                if not job.get("enabled"):
                    continue

                next_run = _parse_time(
                    job.get("next_run")
                )

                if next_run is None:
                    continue

                if next_run <= now:
                    due.append(job)

            # Advance schedules BEFORE execution.
            #
            # This prevents the same job from being launched
            # repeatedly by several heartbeat ticks.
            for job in due:

                job["last_run"] = _iso(now)
                job["run_count"] = (
                    int(job.get("run_count") or 0)
                    + 1
                )

                if job.get("kind") == "interval":

                    interval = int(
                        job.get(
                            "interval_seconds"
                        )
                        or 0
                    )

                    next_run = (
                        _parse_time(
                            job.get("next_run")
                        )
                        or now
                    )

                    # Catch up without executing the same missed
                    # interval hundreds of times after downtime.
                    while next_run <= now:
                        next_run += timedelta(
                            seconds=interval
                        )

                    job["next_run"] = _iso(
                        next_run
                    )

                else:
                    job["enabled"] = False
                    job["next_run"] = None

            self._save()

        launched = []

        if not due:
            return {
                "success": True,
                "launched": [],
                "output": "Scheduler: no jobs due.",
            }

        # Lazy import avoids circular startup dependencies.
        from task_runtime import get_runtime

        runtime = get_runtime()

        for job in due:

            result = runtime.spawn(
                job["goal"],
                session_id=(
                    f"scheduled:{job['id']}"
                ),
            )

            with self._lock:

                current = self._jobs.get(
                    job["id"]
                )

                if current is None:
                    continue

                if result.get("success"):
                    current["last_task_id"] = (
                        result.get("task_id")
                    )
                    current["last_error"] = None

                    launched.append(
                        {
                            "job_id": job["id"],
                            "task_id": result.get(
                                "task_id"
                            ),
                        }
                    )

                else:
                    current["last_error"] = (
                        result.get("error")
                        or result.get("output")
                    )

                    # A one-shot job that could not launch is
                    # re-enabled so the next daemon tick can retry.
                    if job.get("kind") == "once":
                        current["enabled"] = True
                        current["next_run"] = _iso(
                            now + timedelta(
                                seconds=60
                            )
                        )

            self._save()

        return {
            "success": True,
            "launched": launched,
            "output": json.dumps(
                launched,
                ensure_ascii=False,
            ),
        }


_scheduler = None
_scheduler_lock = threading.Lock()


def get_scheduler():
    global _scheduler

    if _scheduler is None:
        with _scheduler_lock:
            if _scheduler is None:
                _scheduler = Scheduler()

    return _scheduler


def schedule_task(
    goal,
    run_at,
    interval_seconds=None,
):
    return get_scheduler().create(
        goal,
        run_at,
        interval_seconds,
    )


def scheduled_tasks(limit=50):
    return get_scheduler().list_jobs(
        limit
    )


def scheduled_task_cancel(job_id):
    return get_scheduler().cancel(
        job_id
    )
