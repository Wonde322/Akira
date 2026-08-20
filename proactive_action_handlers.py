"""Concrete, user-approved handlers for proactive action events."""
from __future__ import annotations


class ProactiveActionHandlers:
    """Translate explicit proactive selections into bounded background work."""

    def __init__(self, spawn):
        self._spawn = spawn

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
        return {"handled": True, "success": bool(result.get("success")), "kind": event_type, "goal": goal, "spawn": result}


def get_proactive_action_handlers(spawn=None):
    if spawn is None:
        from task_runtime import get_runtime
        spawn = get_runtime().spawn
    return ProactiveActionHandlers(spawn)
