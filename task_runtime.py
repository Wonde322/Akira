"""Persistent autonomous task runtime for Akira."""
from __future__ import annotations

import json
import os
import tempfile
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TASK_DIR = ROOT / "runtime" / "tasks"
TASK_FILE = ROOT / "runtime" / "background_tasks.json"
MAX_CONCURRENT_TASKS = 3
MAX_STORED_TASKS = 100
_TERMINAL_STATUSES = {"completed", "failed", "cancelled", "interrupted"}
_ACTIVE_STATUSES = {"queued", "running", "cancelling"}
_VALID_STATUSES = _TERMINAL_STATUSES | _ACTIVE_STATUSES


def _now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


class TaskRuntime:
    """Persistent threaded runtime for autonomous agent work."""

    def __init__(self, max_workers=MAX_CONCURRENT_TASKS):
        if isinstance(max_workers, bool) or int(max_workers) < 1:
            raise ValueError("max_workers must be a positive integer")
        self.max_workers = int(max_workers)
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="akira-bg",
        )
        self._lock = threading.RLock()
        self._tasks = {}
        self._futures = {}
        self._load()

    @staticmethod
    def _normalize_loaded_task(raw):
        if not isinstance(raw, dict):
            return None
        task_id = str(raw.get("id") or "").strip()
        goal = str(raw.get("goal") or "").strip()
        if not task_id or not goal:
            return None
        status = str(raw.get("status") or "failed").strip().lower()
        if status not in _VALID_STATUSES:
            status = "failed"
        if status in _ACTIVE_STATUSES:
            status = "interrupted"
        session_id = str(raw.get("session_id") or f"background:{task_id}").strip()
        task = dict(raw)
        task.update({
            "id": task_id,
            "goal": goal,
            "session_id": session_id or f"background:{task_id}",
            "status": status,
        })
        try:
            task["causation_depth"] = max(0, int(raw.get("causation_depth") or 0))
        except (TypeError, ValueError):
            task["causation_depth"] = 0
        for key in ("parent_event_id", "correlation_id"):
            value = raw.get(key)
            task[key] = str(value).strip() if value is not None and str(value).strip() else None
        for key in ("created_at", "started_at", "finished_at"):
            value = raw.get(key)
            task[key] = str(value) if value is not None else None
        task.setdefault("result", None)
        task.setdefault("error", None)
        return task

    def _load(self):
        TASK_DIR.mkdir(parents=True, exist_ok=True)
        if not TASK_FILE.exists():
            return
        try:
            payload = json.loads(TASK_FILE.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return
        if not isinstance(payload, list):
            return
        interrupted = []
        for raw in payload[-MAX_STORED_TASKS:]:
            task = self._normalize_loaded_task(raw)
            if task is None:
                continue
            if task["status"] == "interrupted":
                task["error"] = "Akira process was restarted before this background task completed."
                task["finished_at"] = _now()
                interrupted.append(dict(task))
            self._tasks[task["id"]] = task
        self._save()
        for task in interrupted:
            self._emit("task.interrupted", self._event_payload(task, error=task["error"]), task)

    def _save(self):
        TASK_DIR.mkdir(parents=True, exist_ok=True)
        payload = list(self._tasks.values())[-MAX_STORED_TASKS:]
        fd, temp_path = tempfile.mkstemp(prefix=".background-tasks-", suffix=".tmp", dir=TASK_FILE.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, TASK_FILE)
        except Exception:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
            raise

    def _active_count(self):
        return sum(task.get("status") in _ACTIVE_STATUSES for task in self._tasks.values())

    def _make_task(self, goal, session_id=None, *, parent_event_id=None, correlation_id=None, causation_depth=0):
        task_id = uuid.uuid4().hex[:12]
        session_id = session_id or f"background:{task_id}"
        if correlation_id is None and str(session_id).startswith("proactive:"):
            correlation_id = str(session_id).split(":", 1)[1] or None
        try:
            depth = max(0, int(causation_depth or 0))
        except (TypeError, ValueError):
            depth = 0
        now = _now()
        return {
            "id": task_id, "goal": str(goal).strip(), "session_id": str(session_id),
            "parent_event_id": parent_event_id, "correlation_id": correlation_id,
            "causation_depth": depth, "status": "queued", "created_at": now,
            "started_at": None, "finished_at": None, "result": None, "error": None,
        }

    @staticmethod
    def _event_payload(task, *, result=None, error=None):
        payload = {"task_id": task.get("id"), "goal": task.get("goal"), "session_id": task.get("session_id")}
        if result is not None:
            payload["result"] = result
        if error is not None:
            payload["error"] = error
        return payload

    def spawn(self, goal, session_id=None, *, parent_event_id=None, correlation_id=None, causation_depth=0):
        goal = str(goal or "").strip()
        if not goal:
            return {"success": False, "error": "empty_goal", "output": "Нельзя создать background task с пустой целью."}
        failed_task = None
        with self._lock:
            if self._active_count() >= self.max_workers:
                return {"success": False, "error": "background_capacity", "output": f"Достигнут лимит одновременно работающих background tasks: {self.max_workers}."}
            task = self._make_task(goal, session_id, parent_event_id=parent_event_id, correlation_id=correlation_id, causation_depth=causation_depth)
            task_id = task["id"]
            self._tasks[task_id] = task
            try:
                future = self._executor.submit(self._run, task_id)
                self._futures[task_id] = future
                if task["status"] not in _TERMINAL_STATUSES:
                    task["status"] = "running"
                    task["started_at"] = _now()
                self._save()
            except Exception as error:
                task.update(status="failed", error=str(error), result=None, finished_at=_now())
                self._save()
                failed_task = dict(task)
        if failed_task:
            self._emit("task.failed", self._event_payload(failed_task, error=failed_task["error"]), failed_task)
            return {"success": False, "error": "task_submit_failed", "task_id": task_id, "status": "failed", "output": f"Не удалось запустить background task: {failed_task['error']}"}
        return {"success": True, "task_id": task_id, "status": task["status"], "goal": goal, "output": f"Background task {task_id} запущен."}

    def cancel(self, task_id, reason="Cancelled by user"):
        task_id = str(task_id)
        emit_task = None
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return {"success": False, "error": "task_not_found", "task_id": task_id}
            if task["status"] in _TERMINAL_STATUSES:
                return {"success": False, "error": "task_not_active", "task_id": task_id, "status": task["status"]}
            future = self._futures.get(task_id)
            if future is not None and future.cancel():
                task.update(status="cancelled", error=str(reason), finished_at=_now())
                self._futures.pop(task_id, None)
                self._save()
                emit_task = dict(task)
            else:
                task.update(status="cancelling", error=str(reason))
                self._save()
        if emit_task:
            self._emit("task.cancelled", self._event_payload(emit_task, error=emit_task["error"]), emit_task)
            return {"success": True, "task_id": task_id, "status": "cancelled"}
        from agent_runtime import get_agent_runtime
        get_agent_runtime().cancel(task_id)
        return {"success": True, "task_id": task_id, "status": "cancelling", "output": "Отмена запрошена. Текущий безопасный шаг завершится, следующий не начнётся."}

    def _run(self, task_id):
        event_type = event_payload = event_task = None
        try:
            with self._lock:
                task = self._tasks.get(task_id)
                if task is None:
                    return None
                if task["status"] in {"cancelled", "cancelling"}:
                    if task["status"] == "cancelling":
                        task.update(status="cancelled", finished_at=_now())
                        self._save()
                        event_type = "task.cancelled"
                        event_payload = self._event_payload(task, error=task.get("error"))
                        event_task = dict(task)
                    return None
                goal, session_id = task["goal"], task["session_id"]
            from agent_runtime import get_agent_runtime
            result = get_agent_runtime().run(goal, session_id=session_id, mode="background", task_id=task_id)
            with self._lock:
                task = self._tasks.get(task_id)
                if task is None:
                    return None
                if task["status"] == "cancelling":
                    task.update(status="cancelled", finished_at=_now())
                    event_type = "task.cancelled"
                    event_payload = self._event_payload(task, error=task.get("error"))
                elif task["status"] != "cancelled":
                    task.update(status="completed", result=str(result), error=None, finished_at=_now())
                    event_type = "task.completed"
                    event_payload = self._event_payload(task, result=str(result))
                event_task = dict(task)
                self._save()
        except Exception as error:
            try:
                from agent_runtime import ExecutionCancelled
                cancelled = isinstance(error, ExecutionCancelled)
            except Exception:
                cancelled = False
            with self._lock:
                task = self._tasks.get(task_id)
                if task is None or task["status"] == "cancelled":
                    return None
                if cancelled or task["status"] == "cancelling":
                    task.update(status="cancelled", finished_at=_now())
                    event_type = "task.cancelled"
                    event_payload = self._event_payload(task, error=task.get("error") or "Cancelled")
                else:
                    task.update(status="failed", error=str(error), result=None, finished_at=_now(), traceback=traceback.format_exc()[-4000:])
                    event_type = "task.failed"
                    event_payload = self._event_payload(task, error=str(error))
                event_task = dict(task)
                self._save()
        finally:
            with self._lock:
                self._futures.pop(task_id, None)
                self._save()
            if event_type:
                self._emit(event_type, event_payload, event_task)
        return None if event_type in {"task.cancelled", "task.failed"} else (event_payload or {}).get("result")

    @staticmethod
    def _emit(event_type, payload, task=None):
        try:
            from event_bus import emit_event
            task = task or {}
            metadata = {"source": "task_runtime"}
            correlation_id = task.get("correlation_id")
            parent_event_id = task.get("parent_event_id") or correlation_id
            if correlation_id:
                metadata["correlation_id"] = correlation_id
            if parent_event_id:
                metadata["parent_event_id"] = parent_event_id
                try:
                    metadata["causation_depth"] = max(0, int(task.get("causation_depth") or 0)) + 1
                except (TypeError, ValueError):
                    metadata["causation_depth"] = 1
            emit_event(event_type, payload, **metadata)
        except Exception as error:
            print("[Akira task runtime] event error:", error)

    def status(self, task_id):
        with self._lock:
            task = self._tasks.get(str(task_id))
            if task is None:
                return {"success": False, "error": "task_not_found", "output": f"Task {task_id} не найден."}
            return {"success": True, "task": dict(task), "output": json.dumps(task, ensure_ascii=False, indent=2)}

    def list_tasks(self, limit=20):
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 20
        limit = max(1, min(limit, 50))
        with self._lock:
            tasks = list(self._tasks.values())[-limit:]
            tasks.reverse()
            return {"success": True, "tasks": [dict(task) for task in tasks], "output": json.dumps(tasks, ensure_ascii=False, indent=2)}

    def result(self, task_id):
        response = self.status(task_id)
        if not response.get("success"):
            return response
        task = response["task"]
        status = task["status"]
        if status == "completed":
            return {"success": True, "ready": True, "task_id": task_id, "result": task.get("result"), "output": str(task.get("result") or "")}
        if status in _TERMINAL_STATUSES:
            return {"success": False, "ready": True, "task_id": task_id, "error": task.get("error"), "status": status, "output": f"Background task {status}: {task.get('error') or ''}"}
        return {"success": True, "ready": False, "task_id": task_id, "status": status, "output": f"Task {task_id} ещё выполняется."}

    def shutdown(self, wait=True):
        self._executor.shutdown(wait=bool(wait), cancel_futures=True)


_runtime = None
_runtime_lock = threading.Lock()


def get_runtime():
    global _runtime
    if _runtime is None:
        with _runtime_lock:
            if _runtime is None:
                _runtime = TaskRuntime()
    return _runtime


def spawn_task(goal, session_id=None, **kwargs):
    return get_runtime().spawn(goal, session_id=session_id, **kwargs)


def task_status(task_id):
    return get_runtime().status(task_id)


def task_result(task_id):
    return get_runtime().result(task_id)


def cancel_task(task_id, reason="Cancelled by user"):
    return get_runtime().cancel(task_id, reason)


def list_tasks(limit=20):
    return get_runtime().list_tasks(limit)
