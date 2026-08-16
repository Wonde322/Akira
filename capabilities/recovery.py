"""Adaptive recovery policy for Akira computer-use tasks.

Recovery does not execute actions.
It classifies failures and produces alternative universal capabilities
for the reasoning/router layer.

Flow:

    action
      -> result
      -> classify failure
      -> fallback capabilities
      -> fresh observation
      -> different action
"""

from __future__ import annotations


ERROR_FALLBACKS = {
    "target_required": (
        "observe",
        "open",
    ),
    "target_not_frontmost": (
        "observe",
        "open",
        "key",
    ),
    "activate_failed": (
        "observe",
        "open",
        "key",
    ),
    "out_of_bounds": (
        "observe",
        "screen_size",
    ),
    "invalid_coordinate": (
        "observe",
        "screen_size",
    ),
    "backend_unavailable": (
        "observe",
        "shell",
    ),
    "execution_error": (
        "observe",
        "key",
        "open",
        "shell",
    ),
    "error": (
        "observe",
        "key",
        "open",
        "shell",
    ),
    "permission": (
        "observe",
    ),
    "denied": (
        "observe",
    ),
}


ACTION_FALLBACKS = {
    "click": (
        "observe",
        "select",
        "key",
        "open",
    ),
    "select": (
        "observe",
        "click",
        "key",
        "open",
    ),
    "type": (
        "observe",
        "open",
        "key",
    ),
    "key": (
        "observe",
        "click",
        "type",
        "open",
    ),
    "scroll": (
        "observe",
        "click",
        "key",
    ),
    "drag": (
        "observe",
        "click",
        "select",
        "key",
    ),
    "open": (
        "observe",
        "key",
        "shell",
    ),
    "close": (
        "observe",
        "key",
        "shell",
    ),
    "shell": (
        "observe",
        "find",
        "read",
        "open",
    ),
    "write": (
        "read",
        "find",
        "shell",
        "observe",
    ),
    "create": (
        "find",
        "read",
        "shell",
        "observe",
    ),
    "move": (
        "find",
        "read",
        "shell",
        "observe",
    ),
    "copy": (
        "find",
        "read",
        "shell",
        "observe",
    ),
    "rename": (
        "find",
        "read",
        "shell",
        "observe",
    ),
    "delete": (
        "find",
        "read",
        "shell",
        "observe",
    ),
}


def classify_failure(action, result):
    """Classify a failed tool result and produce fallback capabilities."""

    action = str(action or "").strip()
    result = result if isinstance(result, dict) else {}

    if result.get("success"):
        return {
            "failed": False,
            "action": action,
            "error": None,
            "reason": "",
            "output": "",
            "fallback_tools": [],
            "avoid_same_action": False,
            "force_observe": False,
        }

    error = str(result.get("error") or "").strip()
    output = str(result.get("output") or "").strip()

    fallback = list(
        ERROR_FALLBACKS.get(
            error,
            ACTION_FALLBACKS.get(
                action,
                ("observe",),
            ),
        )
    )

    # Никогда не предлагаем тупо повторить тот же failed action.
    fallback = [
        tool
        for tool in fallback
        if tool != action
    ]

    if not fallback:
        fallback = ["observe"]

    if error in {
        "out_of_bounds",
        "invalid_coordinate",
        "target_not_frontmost",
        "activate_failed",
    }:
        reason = (
            "GUI state is stale or inconsistent. "
            "Refresh observation before choosing another action."
        )
        force_observe = True

    elif error in {
        "backend_unavailable",
        "execution_error",
        "error",
    }:
        reason = (
            "The current execution route failed. "
            "Choose another universal capability instead of repeating it."
        )
        force_observe = True

    elif error in {
        "denied",
        "permission",
    }:
        reason = (
            "The action is governed by permissions. "
            "Do not blindly retry the same action."
        )
        force_observe = True

    else:
        reason = (
            "The requested route failed. "
            "Use the failure as evidence and choose a different route."
        )
        force_observe = True

    return {
        "failed": True,
        "action": action,
        "error": error,
        "reason": reason,
        "output": output[:1200],
        "fallback_tools": fallback,
        "avoid_same_action": True,
        "force_observe": force_observe,
    }


def recovery_tools(action, result):
    """Return fallback capability names."""

    return classify_failure(
        action,
        result,
    )["fallback_tools"]


def should_force_observe(action, result):
    """Return whether a failed action requires fresh observation."""

    return bool(
        classify_failure(
            action,
            result,
        ).get("force_observe")
    )


def recovery_context(action, result):
    """Return complete structured recovery context."""

    return classify_failure(
        action,
        result,
    )
