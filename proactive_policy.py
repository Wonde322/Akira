"""Reasoning policy for choosing how Akira should react to contextual events.

The policy is deterministic and side-effect free. Explicit user choices may
suppress repeatedly unwanted questions, but ambient behaviour is never treated
as feedback.
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
                 very_strong_confidence=0.85, long_dwell_seconds=30 * 60,
                 feedback_store=None):
        self.weak_confidence = float(weak_confidence)
        self.strong_confidence = float(strong_confidence)
        self.very_strong_confidence = float(very_strong_confidence)
        self.long_dwell_seconds = float(long_dwell_seconds)
        if feedback_store is None:
            from proactive_feedback import get_proactive_feedback_store
            feedback_store = get_proactive_feedback_store()
        self.feedback_store = feedback_store

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

    def _respect_feedback(self, recommendation):
        if recommendation.action != "ask_user":
            return recommendation
        if not self.feedback_store.should_suppress_question(recommendation.reason):
            return recommendation
        return PolicyRecommendation(
            "notify", recommendation.reason + "_feedback_suppressed",
            recommendation.notification, priority="low", goal=recommendation.goal,
        )

    def decide(self, event_type, payload):
        payload = payload or {}
        goal, confidence = self._task(payload)
        if not goal:
            return None
        if confidence < self.weak_confidence:
            return PolicyRecommendation("record", "weak_task_context", priority="low")

        recommendation = None
        if event_type == "desktop.context.repeated":
            count = max(0, int(payload.get("count") or 0))
            if confidence >= self.strong_confidence and count >= 3:
                recommendation = PolicyRecommendation(
                    "ask_user", "repeated_task_context",
                    f"Похоже, ты уже несколько раз возвращаешься к задаче «{goal}». Нужна помощь?",
                    priority="normal", goal=goal,
                )
            else:
                recommendation = PolicyRecommendation("notify", "repeated_task_context_low_confidence",
                                                      f"Похоже, это снова связано с задачей «{goal}».", priority="low", goal=goal)
        elif event_type == "desktop.context.dwell":
            try:
                seconds = float(payload.get("seconds") or 0.0)
            except (TypeError, ValueError):
                seconds = 0.0
            if confidence >= self.very_strong_confidence and seconds >= self.long_dwell_seconds:
                recommendation = PolicyRecommendation(
                    "ask_user", "long_task_dwell",
                    f"Ты уже довольно долго работаешь над «{goal}». Хочешь, я помогу или что-нибудь проверю?",
                    priority="normal", goal=goal,
                )
            else:
                recommendation = PolicyRecommendation("notify", "task_context_dwell",
                                                      f"Ты всё ещё работаешь над «{goal}».", priority="low", goal=goal)
        return self._respect_feedback(recommendation) if recommendation is not None else None


def get_proactive_reasoning_policy():
    return ProactiveReasoningPolicy()
