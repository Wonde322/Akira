"""Detect stalled and interrupted background tasks and emit durable events."""
from __future__ import annotations

from datetime import datetime
import threading

DEFAULT_STALL_SECONDS = 60 * 10


class TaskWatchdog:
    def __init__(self, runtime=None, stall_seconds=DEFAULT_STALL_SECONDS, now=None, emit=None):
        self._runtime = runtime
        self.stall_seconds = float(stall_seconds)
        self._now = now or datetime.now
        self._emit = emit
        self._lock = threading.RLock()
        self._reported = set()

    def _event_key(self, task, kind):
        return kind, str(task.get("id") or "")

    def _emit_failure(self, kind, task, error, extra=None):
        key = self._event_key(task, kind)
        with self._lock:
            if key in self._reported:
                return None
            self._reported.add(key)

        payload = {
            "task_id": task.get("id"),
            "goal": task.get("goal"),
            "session_id": task.get("session_id"),
            "status": task.get("status"),
            "error": error,
            "watchdog_kind": kind,
        }
        if extra:
            payload.update(extra)
        try:
            emitter = self._emit
            if emitter is None:
                from event_bus import emit_event
                emitter = emit_event
            return emitter("task.failed", payload, source="task_watchdog")
        except Exception:
            with self._lock:
                self._reported.discard(key)
            return None

    def scan(self):
        runtime = self._runtime
        if runtime is None:
            from task_runtime import get_runtime
            runtime = get_runtime()

        response = runtime.list_tasks(limit=50)
        tasks = response.get("tasks") if isinstance(response, dict) else []
        if not isinstance(tasks, list):
            tasks = []

        stalled = []
        interrupted = []
        now = self._now()

        for task in tasks:
            if not isinstance(task, dict) or not task.get("id"):
                continue
            status = task.get("status")
            if status == "interrupted":
                error = str(task.get("error") or "Фоновая задача была прервана после перезапуска Akira.")
                event = self._emit_failure("interrupted", task, error)
                if event is not None:
                    interrupted.append(str(task["id"]))
                continue

            if status != "running":
                continue
            started_at = task.get("started_at")
            try:
                started = datetime.fromisoformat(str(started_at))
                age = max(0.0, (now - started).total_seconds())
            except Exception:
                continue
            if age < self.stall_seconds:
                continue
            error = f"Фоновая задача не завершилась за {int(age)} секунд и считается зависшей."
            event = self._emit_failure("stalled", task, error, {
                "age_seconds": round(age, 3),
                "stall_seconds": self.stall_seconds,
            })
            if event is not None:
                stalled.append(str(task["id"]))

        return {
            "success": True,
            "stalled": stalled,
            "interrupted": interrupted,
            "checked": len(tasks),
        }


_watchdog = None
_watchdog_lock = threading.Lock()


def get_task_watchdog():
    global _watchdog
    if _watchdog is None:
        with _watchdog_lock:
            if _watchdog is None:
                _watchdog = TaskWatchdog()
    return _watchdog
