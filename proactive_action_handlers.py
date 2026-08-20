"""Concrete, user-approved handlers for proactive action events."""
from __future__ import annotations


class ProactiveActionHandlers:
    """Translate explicit proactive selections into bounded background work."""

    def __init__(self, spawn, lifecycle=None):
        self._spawn = spawn
        self._lifecycle = lifecycle

    @staticmethod
    def _goal(payload):
        proposal = payload.get("proposal") or {}
        return str(payload.get("goal") or proposal.get("goal") or "").strip()

    def handle(self, event):
        event = dict(event or {})
        event_type = str(event.get("type") or "")
        payload = event.get("payload") or {}
        correlation_id = event.get("correlation_id") or event.get("id") or "proactive"

        if event_type == "proactive.dismissed":
            return {"handled": True, "success": True, "kind": "dismiss"}

        if event_type == "proactive.help_requested":
            goal = self._goal(payload)
            if not goal:
                goal = "Помоги пользователю разобраться с текущей задачей и предложи следующий шаг."
        elif event_type == "proactive.inspect_requested":
            goal = self._goal(payload)
            if goal:
                goal = "Проверь текущий контекст, связанный с задачей: " + goal
            else:
                goal = "Проверь текущий desktop context и кратко опиши, что требует внимания."
        else:
            return {"handled": False}

        result = self._spawn(goal, session_id="proactive:" + str(correlation_id))
        lifecycle_item = None
        if result.get("success") and self._lifecycle is not None:
            lifecycle_item = self._lifecycle.started(
                result.get("task_id"), goal, kind=event_type, correlation_id=correlation_id,
            )
        return {"handled": True, "success": bool(result.get("success")), "kind": event_type,
                "goal": goal, "spawn": result, "lifecycle": lifecycle_item}


def get_proactive_action_handlers(spawn=None, lifecycle=None):
    if spawn is None:
        from task_runtime import get_runtime
        spawn = get_runtime().spawn
    if lifecycle is None:
        from proactive_action_lifecycle import get_proactive_action_lifecycle
        lifecycle = get_proactive_action_lifecycle()
    return ProactiveActionHandlers(spawn, lifecycle=lifecycle)
