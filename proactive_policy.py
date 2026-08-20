"""Reasoning policy for choosing how Akira should react to contextual events.

The policy is deliberately deterministic and side-effect free. It turns observed
signals plus task relevance into an action recommendation; the runtime remains
responsible for delivery and task execution.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyRecommendation:
    action: str
    reason: str
    notification: str | None = None
    priority: str = "normal"
    goal: str | None = None


class ProactiveReasoningPolicy:
    def __init__(self, weak_confidence=0.3, strong_confidence=0.7,
                 very_strong_confidence=0.85, long_dwell_seconds=30 * 60):
        self.weak_confidence = float(weak_confidence)
        self.strong_confidence = float(strong_confidence)
        self.very_strong_confidence = float(very_strong_confidence)
        self.long_dwell_seconds = float(long_dwell_seconds)

    @staticmethod
    def _task(payload):
        task = payload.get("active_task") or {}
        if not isinstance(task, dict):
            return None, 0.0
        goal = str(task.get("goal") or "").strip()
        try:
            confidence = float(task.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        return goal or None, max(0.0, min(1.0, confidence))

    def decide(self, event_type, payload):
        payload = payload or {}
        goal, confidence = self._task(payload)
        if not goal:
            return None
        if confidence < self.weak_confidence:
            return PolicyRecommendation("record", "weak_task_context", priority="low")

        if event_type == "desktop.context.repeated":
            count = max(0, int(payload.get("count") or 0))
            if confidence >= self.strong_confidence and count >= 3:
                return PolicyRecommendation(
                    "ask_user", "repeated_task_context",
                    f"Похоже, ты уже несколько раз возвращаешься к задаче «{goal}». Нужна помощь?",
                    priority="normal",
                )
            return PolicyRecommendation("notify", "repeated_task_context_low_confidence",
                                        f"Похоже, это снова связано с задачей «{goal}».", priority="low")

        if event_type == "desktop.context.dwell":
            try:
                seconds = float(payload.get("seconds") or 0.0)
            except (TypeError, ValueError):
                seconds = 0.0
            if confidence >= self.very_strong_confidence and seconds >= self.long_dwell_seconds:
                return PolicyRecommendation(
                    "ask_user", "long_task_dwell",
                    f"Ты уже довольно долго работаешь над «{goal}». Хочешь, я помогу или что-нибудь проверю?",
                    priority="normal",
                )
            return PolicyRecommendation("notify", "task_context_dwell",
                                        f"Ты всё ещё работаешь над «{goal}».", priority="low")
        return None


def get_proactive_reasoning_policy():
    return ProactiveReasoningPolicy()
