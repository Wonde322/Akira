"""Execution policy selection for Akira.

The runtime has one execution boundary but not every request deserves the same
reasoning budget. Policies describe how much autonomy an execution is allowed to
use; they do not create separate agent implementations.
"""
from __future__ import annotations

from enum import Enum
import re


class ExecutionPolicy(str, Enum):
    DIRECT = "direct"
    CONTROLLED = "controlled"
    AGENT = "agent"
    AUTONOMOUS = "autonomous"


_SIMPLE_PREFIXES = (
    "открой ", "закрой ", "покажи ", "скажи ", "включи ",
    "выключи ", "поставь ", "убавь ", "прибавь ", "прочитай ",
)

_CONTROLLED_TERMS = {
    "открыть", "закрыть", "создать", "записать", "прочитать",
    "найти", "скопировать", "переместить", "переименовать", "удалить",
    "open", "close", "create", "write", "read", "find", "copy",
    "move", "rename", "delete",
}

_COMPLEX_TERMS = {
    "сравни", "исследуй", "разберись", "проанализируй", "спланируй",
    "подготовь", "проверь", "найди варианты", "самостоятельно",
    "compare", "research", "analyze", "plan", "prepare",
}


def normalize_policy(value, *, background=False):
    """Normalize explicit policy/mode aliases without guessing silently."""
    if background:
        return ExecutionPolicy.AUTONOMOUS

    raw = str(value or "auto").strip().lower()
    aliases = {
        "foreground": "auto",
        "background": "autonomous",
        "auto": "auto",
        "direct": "direct",
        "controlled": "controlled",
        "agent": "agent",
        "autonomous": "autonomous",
    }
    raw = aliases.get(raw, raw)
    if raw == "auto":
        return None
    try:
        return ExecutionPolicy(raw)
    except ValueError:
        raise ValueError(f"Unknown execution policy: {value}")


def choose_execution_policy(goal, *, mode="auto", background=False):
    """Choose the narrowest safe execution policy for a request.

    Explicit policies always win. Background execution is autonomous because the
    caller is intentionally not waiting for the work to finish.
    """
    explicit = normalize_policy(mode, background=background)
    if explicit is not None:
        return explicit

    text = re.sub(r"\s+", " ", str(goal or "").strip().lower())
    if not text:
        return ExecutionPolicy.AGENT

    if any(term in text for term in _COMPLEX_TERMS):
        return ExecutionPolicy.AGENT

    if text.startswith(_SIMPLE_PREFIXES) and len(text.split()) <= 8:
        return ExecutionPolicy.DIRECT

    tokens = set(re.findall(r"[a-zа-яё]+", text, flags=re.IGNORECASE))
    if tokens & _CONTROLLED_TERMS and len(text.split()) <= 18:
        return ExecutionPolicy.CONTROLLED

    return ExecutionPolicy.AGENT
