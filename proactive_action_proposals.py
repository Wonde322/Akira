"""Build safe, concrete next-step proposals for proactive questions.

This layer never executes anything. It only converts a high-signal contextual
problem into a small set of explicit user choices that can later be rendered by
any UI surface.
"""
from __future__ import annotations


class ProactiveActionProposer:
    @staticmethod
    def propose(event_type, payload, recommendation):
        payload = payload or {}
        goal = str(getattr(recommendation, "goal", None) or (payload.get("active_task") or {}).get("goal") or "").strip()
        if not goal:
            return []
        reason = str(getattr(recommendation, "reason", ""))
        if reason == "repeated_task_context":
            return [
                {"id": "help", "label": "Помоги разобраться", "kind": "ask"},
                {"id": "inspect", "label": "Проверь текущий контекст", "kind": "observe"},
                {"id": "continue", "label": "Я сам продолжу", "kind": "dismiss"},
            ]
        if reason == "long_task_dwell":
            return [
                {"id": "inspect", "label": "Проверь, что происходит", "kind": "observe"},
                {"id": "help", "label": "Предложи следующий шаг", "kind": "ask"},
                {"id": "continue", "label": "Пока не вмешивайся", "kind": "dismiss"},
            ]
        return []


_proposer = ProactiveActionProposer()


def get_proactive_action_proposer():
    return _proposer
