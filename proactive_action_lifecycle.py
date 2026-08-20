"""Track the lifecycle of user-approved proactive actions."""
from __future__ import annotations

import threading
from datetime import datetime


class ProactiveActionLifecycle:
    """Small in-memory projection keyed by background task id."""

    def __init__(self, clock=None):
        self._clock = clock or (lambda: datetime.now().astimezone().isoformat(timespec="seconds"))
        self._lock = threading.RLock()
        self._items = {}

    def started(self, task_id, goal, *, kind=None, correlation_id=None):
        item = {
            "task_id": str(task_id), "goal": str(goal or "").strip(),
            "kind": kind, "correlation_id": correlation_id,
            "status": "running", "result": None, "error": None,
            "started_at": self._clock(), "finished_at": None,
        }
        with self._lock:
            self._items[item["task_id"]] = item
        return dict(item)

    def completed(self, task_id, result=None):
        return self._finish(task_id, "completed", result=result)

    def failed(self, task_id, error=None):
        return self._finish(task_id, "failed", error=error)

    def _finish(self, task_id, status, *, result=None, error=None):
        with self._lock:
            item = self._items.get(str(task_id))
            if item is None:
                return None
            item["status"] = status
            item["result"] = None if result is None else str(result)
            item["error"] = None if error is None else str(error)
            item["finished_at"] = self._clock()
            return dict(item)

    def get(self, task_id):
        with self._lock:
            item = self._items.get(str(task_id))
            return None if item is None else dict(item)

    def recent(self, limit=20):
        try: limit = int(limit)
        except Exception: limit = 20
        limit = max(1, min(limit, 100))
        with self._lock:
            return [dict(item) for item in list(self._items.values())[-limit:]][::-1]


_lifecycle = None
_lifecycle_lock = threading.Lock()

def get_proactive_action_lifecycle():
    global _lifecycle
    if _lifecycle is None:
        with _lifecycle_lock:
            if _lifecycle is None:
                _lifecycle = ProactiveActionLifecycle()
    return _lifecycle
