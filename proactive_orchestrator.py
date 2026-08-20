"""Conservative autonomous orchestration for proactive desktop signals."""
from __future__ import annotations

import threading
import time


class ProactiveOrchestrator:
    """Decides when a high-signal context pattern deserves a safe background check.

    This layer deliberately does not execute UI actions. It can only request a
    background investigation, which still goes through the normal task runtime
    and permission system.
    """

    def __init__(self, min_confidence=0.85, min_repeats=3,
                 min_dwell_seconds=30 * 60, cooldown_seconds=20 * 60,
                 max_active=2, clock=None):
        self.min_confidence = float(min_confidence)
        self.min_repeats = max(2, int(min_repeats))
        self.min_dwell_seconds = float(min_dwell_seconds)
        self.cooldown_seconds = float(cooldown_seconds)
        self.max_active = max(1, int(max_active))
        self._clock = clock or time.monotonic
        self._lock = threading.RLock()
        self._last = {}
        self._active = set()

    @staticmethod
    def _task(payload):
        task = payload.get("active_task") or {}
        if not isinstance(task, dict):
            return None
        task_id = str(task.get("id") or "").strip()
        goal = str(task.get("goal") or "").strip()
        if not task_id or not goal:
            return None
        if str(task.get("status") or "running").lower() not in {"running", "active", "queued"}:
            return None
        return task_id, goal

    def _eligible(self, event_type, payload):
        task = self._task(payload)
        if task is None:
            return None
        try:
            confidence = float((payload.get("active_task") or {}).get("confidence") or 0)
        except (TypeError, ValueError):
            confidence = 0.0
        if confidence < self.min_confidence:
            return None
        if event_type == "desktop.context.repeated":
            try:
                if int(payload.get("count") or 0) < self.min_repeats:
                    return None
            except (TypeError, ValueError):
                return None
            return task
        if event_type == "desktop.context.dwell":
            try:
                if float(payload.get("seconds") or 0) < self.min_dwell_seconds:
                    return None
            except (TypeError, ValueError):
                return None
            return task
        return None

    def decide(self, event_type, payload, now=None):
        now = self._clock() if now is None else float(now)
        task = self._eligible(str(event_type), payload or {})
        if task is None:
            return {"spawn": False, "reason": "insufficient_signal"}
        task_id, goal = task
        with self._lock:
            if task_id in self._active:
                return {"spawn": False, "reason": "task_already_active", "task_id": task_id}
            if len(self._active) >= self.max_active:
                return {"spawn": False, "reason": "active_limit"}
            previous = self._last.get(task_id)
            if previous is not None and now - previous < self.cooldown_seconds:
                return {"spawn": False, "reason": "cooldown", "task_id": task_id}
            self._last[task_id] = now
            self._active.add(task_id)
        context = payload.get("context") or {}
        app = str(context.get("app") or "").strip()
        title = str(context.get("title") or "").strip()
        location = " — ".join(part for part in (app, title) if part) or "текущем контексте"
        investigation = (
            f"Проверь текущий контекст, связанный с активной задачей «{goal}». "
            f"Пользователь несколько раз возвращается к {location} или долго там работает. "
            "Сначала собери информацию и проанализируй ситуацию. Не выполняй изменений "
            "и не взаимодействуй с интерфейсом без обычного подтверждения пользователя."
        )
        return {
            "spawn": True,
            "reason": "high_signal_context_pattern",
            "task_id": task_id,
            "goal": investigation,
            "source_goal": goal,
        }

    def release(self, source_task_id):
        with self._lock:
            self._active.discard(str(source_task_id or ""))

    def active_source_tasks(self):
        with self._lock:
            return sorted(self._active)


_orchestrator = None
_orchestrator_lock = threading.Lock()


def get_proactive_orchestrator():
    global _orchestrator
    if _orchestrator is None:
        with _orchestrator_lock:
            if _orchestrator is None:
                _orchestrator = ProactiveOrchestrator()
    return _orchestrator
