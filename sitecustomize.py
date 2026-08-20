"""Startup guardrails for durable identity memory.

Python imports ``sitecustomize`` before application modules when the project
root is on ``sys.path``. The guard therefore protects every entry point that
imports ``memory`` without changing individual callers.
"""

from __future__ import annotations

import re

import memory as _memory


_ASSISTANT_NAMES = {
    "akira",
    "акира",
    "кира",
    "акера",
}

_IDENTITY_MARKERS = (
    "preferred_name",
    "user_name",
    "name",
    "имя",
    "предпочтительное имя",
    "предпочитаемое имя",
    "актуальный проект имени",
)

_original_remember_memory = _memory.remember_memory
_original_load_memory = _memory.load_memory
_original_save_memory = _memory.save_memory


def _normalize(value: object) -> str:
    return re.sub(r"[^a-zа-яё0-9]+", " ", str(value or "").lower()).strip()


def _is_identity_key(key: object) -> bool:
    normalized = _normalize(key)
    if not normalized:
        return False
    return any(marker in normalized for marker in _IDENTITY_MARKERS)


def _assistant_name(value: object) -> bool:
    normalized = _normalize(value)
    return normalized in _ASSISTANT_NAMES


def _identity_value_mentions_assistant(value: object) -> bool:
    normalized = _normalize(value)
    tokens = set(normalized.split())
    return bool(tokens & _ASSISTANT_NAMES)


def _guarded_remember_memory(
    content: str,
    kind: str = "fact",
    key: str = "",
    source: str = "user",
    importance: float = 0.7,
):
    """Prevent the assistant's own name from becoming user identity memory."""

    if _is_identity_key(key) and _identity_value_mentions_assistant(content):
        return {
            "success": False,
            "error": "assistant_identity_memory_blocked",
            "output": "Нельзя сохранить имя Акиры как имя пользователя.",
        }

    return _original_remember_memory(
        content=content,
        kind=kind,
        key=key,
        source=source,
        importance=importance,
    )


def _guarded_load_memory():
    memory = _original_load_memory()
    preferences = memory.get("preferences", [])
    filtered = [
        item
        for item in preferences
        if not (
            _is_identity_key(item.get("key"))
            and _identity_value_mentions_assistant(item.get("value"))
        )
    ]

    if len(filtered) != len(preferences):
        memory["preferences"] = filtered
        _original_save_memory(memory)

    return memory


_memory.remember_memory = _guarded_remember_memory
_memory.load_memory = _guarded_load_memory
