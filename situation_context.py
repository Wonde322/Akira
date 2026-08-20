"""Build a normalized, side-effect free snapshot of Akira's current situation."""
from __future__ import annotations

from datetime import datetime, timezone

PRIORITY_WEIGHTS = {"low": 0.25, "normal": 0.5, "high": 0.75, "critical": 1.0}


class SituationContextBuilder:
    def __init__(self, task_provider=None, schedule_provider=None, clock=None):
        self.task_provider = task_provider or (lambda: [])
        self.schedule_provider = schedule_provider or (lambda: [])
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _items(provider):
        try:
            value = provider()
        except Exception:
            return []
        if isinstance(value, dict):
            value = value.get("tasks") or value.get("items") or []
        return list(value) if isinstance(value, (list, tuple)) else []

    @staticmethod
    def _active(items):
        return [item for item in items if isinstance(item, dict) and str(item.get("status") or "").lower() not in {"completed", "failed", "cancelled", "interrupted"}]

    @staticmethod
    def _deadline_score(goal):
        try:
            urgency = float(goal.get("urgency") or 0.0)
        except (TypeError, ValueError):
            urgency = 0.0
        priority = PRIORITY_WEIGHTS.get(str(goal.get("priority") or "normal").lower(), 0.5)
        return max(0.0, min(1.0, max(urgency, priority)))

    def build(self, desktop_context=None, active_task=None, active_goal=None):
        desktop = dict(desktop_context or {}) if isinstance(desktop_context, dict) else {}
        task = dict(active_task or {}) if isinstance(active_task, dict) else None
        goal = dict(active_goal or {}) if isinstance(active_goal, dict) else None
        tasks = self._active(self._items(self.task_provider))
        schedules = self._active(self._items(self.schedule_provider))
        score = self._deadline_score(goal or {}) if goal else 0.0
        if task:
            try:
                score = max(score, float(task.get("confidence") or 0.0) * 0.6)
            except (TypeError, ValueError):
                pass
        if schedules:
            score = max(score, 0.4)
        pressure = "critical" if score >= 0.95 else "high" if score >= 0.7 else "normal" if score >= 0.35 else "low"
        timestamp = self.clock()
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        else:
            timestamp = timestamp.astimezone(timezone.utc)
        return {
            "desktop": desktop,
            "active_task": task,
            "active_goal": goal,
            "background": {"active_count": len(tasks)},
            "schedule": {"active_count": len(schedules)},
            "pressure": pressure,
            "pressure_score": round(max(0.0, min(1.0, score)), 3),
            "timestamp": timestamp.isoformat(timespec="seconds"),
        }


def get_situation_context_builder():
    return SituationContextBuilder()
