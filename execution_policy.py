"""Policy selection for one Akira execution.

Policies decide how much agentic machinery a request is allowed to use. They do
not create separate brains: AgentRuntime remains the single execution boundary.
"""
from __future__ import annotations

from enum import Enum


class ExecutionPolicy(str, Enum):
    DIRECT = "direct"
    CONTROLLED = "controlled"
    AGENT = "agent"
    AUTONOMOUS = "autonomous"


def choose_execution_policy(goal, *, mode="foreground", requested=None):
    if requested is not None:
        try:
            return ExecutionPolicy(str(requested))
        except ValueError:
            pass

    if str(mode) == "background":
        return ExecutionPolicy.AUTONOMOUS

    text = str(goal or "").strip().lower()
    if len(text) <= 80 and not any(marker in text for marker in (
        " и ", "потом", "после", "найди", "сравни", "подготов", "исслед",
        "проверь", "создай план", "несколько", "самостоятельно",
    )):
        return ExecutionPolicy.DIRECT

    if any(marker in text for marker in (
        "открой", "закрой", "включи", "выключи", "напиши", "поставь",
    )) and len(text) <= 180:
        return ExecutionPolicy.CONTROLLED

    return ExecutionPolicy.AGENT
