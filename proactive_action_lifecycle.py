"""Persistent lifecycle tracking for user-approved proactive actions."""
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_FILE = ROOT / "runtime" / "proactive_action_lifecycle.json"
TERMINAL_STATUSES = {"completed", "failed", "cancelled", "interrupted"}
KNOWN_STATUSES = TERMINAL_STATUSES | {"running"}


class ProactiveActionLifecycle:
    """Thread-safe projection of proactive actions, persisted across restarts."""

    def __init__(self, clock=None, path=None):
        self._clock = clock or (lambda: datetime.now().astimezone().isoformat(timespec="seconds"))
        self._path = Path(path) if path is not None else DEFAULT_FILE
        self._lock = threading.RLock()
        self._items = {}
        self._load()

    def _load(self):
        changed = False
        try:
            if not self._path.exists(): return
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(payload, list): return
            for raw in payload:
                if not isinstance(raw, dict):
                    changed = True; continue
                task_id = str(raw.get("task_id") or "").strip()
                goal = str(raw.get("goal") or "").strip()
                if not task_id or not goal:
                    changed = True; continue
                item = dict(raw)
                item["task_id"] = task_id; item["goal"] = goal
                status = str(item.get("status") or "running").strip().lower()
                if status not in KNOWN_STATUSES:
                    status = "running"; changed = True
                item["status"] = status
                if self._items.get(task_id) is not None: changed = True
                self._items[task_id] = item
            if changed: self._save()
        except Exception: return

    def _save(self):
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            tmp.write_text(json.dumps(list(self._items.values())[-200:], ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            tmp.replace(self._path)
        except Exception: pass

    def started(self, task_id, goal, *, kind=None, correlation_id=None):
        task_id = str(task_id or "").strip()
        if not task_id: return None
        item = {"task_id": task_id, "goal": str(goal or "").strip(), "kind": kind, "correlation_id": correlation_id, "status": "running", "result": None, "error": None, "started_at": self._clock(), "finished_at": None}
        with self._lock:
            self._items[item["task_id"]] = item; self._save()
        return dict(item)

    def completed(self, task_id, result=None): return self._finish(task_id, "completed", result=result)
    def failed(self, task_id, error=None): return self._finish(task_id, "failed", error=error)
    def cancelled(self, task_id, reason="Cancelled by user"): return self._finish(task_id, "cancelled", error=reason)
    def interrupted(self, task_id, reason="Akira was restarted before this action completed."): return self._finish(task_id, "interrupted", error=reason)

    def _finish(self, task_id, status, *, result=None, error=None):
        with self._lock:
            item = self._items.get(str(task_id))
            if item is None or item.get("status") in TERMINAL_STATUSES: return None if item is None else dict(item)
            item["status"] = status; item["result"] = None if result is None else str(result); item["error"] = None if error is None else str(error); item["finished_at"] = self._clock(); self._save()
            return dict(item)

    def reconcile(self, tasks):
        task_map = {}
        for task in tasks or []:
            if not isinstance(task, dict): continue
            task_id = str(task.get("id") or "").strip()
            if task_id: task_map[task_id] = task
        changed = []
        with self._lock:
            for task_id, item in self._items.items():
                if item.get("status") in TERMINAL_STATUSES: continue
                task = task_map.get(task_id)
                if task is None:
                    if not task_map:
                        item["status"] = "interrupted"; item["result"] = None; item["error"] = "Task disappeared before lifecycle reconciliation."; item["finished_at"] = self._clock(); changed.append(dict(item))
                    continue
                status = str(task.get("status") or "").strip().lower()
                if status == "completed":
                    item["status"] = "completed"; item["result"] = None if task.get("result") is None else str(task.get("result")); item["finished_at"] = task.get("finished_at") or self._clock(); changed.append(dict(item))
                elif status == "failed":
                    item["status"] = "failed"; item["error"] = None if task.get("error") is None else str(task.get("error")); item["finished_at"] = task.get("finished_at") or self._clock(); changed.append(dict(item))
                elif status == "cancelled":
                    item["status"] = "cancelled"; item["result"] = None; item["error"] = task.get("error") or "Cancelled by user"; item["finished_at"] = task.get("finished_at") or self._clock(); changed.append(dict(item))
                elif status == "interrupted":
                    item["status"] = "interrupted"; item["result"] = None; item["error"] = task.get("error") or "Akira was restarted before this action completed."; item["finished_at"] = task.get("finished_at") or self._clock(); changed.append(dict(item))
            if changed: self._save()
        return changed

    def get(self, task_id):
        with self._lock:
            item = self._items.get(str(task_id)); return None if item is None else dict(item)
    def active(self):
        with self._lock: return [dict(item) for item in self._items.values() if item.get("status") not in TERMINAL_STATUSES]
    def recent(self, limit=20):
        try: limit = int(limit)
        except Exception: limit = 20
        limit = max(1, min(limit, 100))
        with self._lock: return [dict(item) for item in list(self._items.values())[-limit:]][::-1]

_lifecycle = None
_lifecycle_lock = threading.Lock()
def get_proactive_action_lifecycle():
    global _lifecycle
    if _lifecycle is None:
        with _lifecycle_lock:
            if _lifecycle is None: _lifecycle = ProactiveActionLifecycle()
    return _lifecycle
