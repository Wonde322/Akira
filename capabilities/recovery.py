"""Adaptive recovery policy for Akira computer-use tasks."""
from __future__ import annotations

ERROR_FALLBACKS = {
    "target_required": ("observe", "open"), "target_not_frontmost": ("observe", "open", "key"),
    "activate_failed": ("observe", "open", "key"), "out_of_bounds": ("observe", "key", "open"),
    "invalid_coordinate": ("observe", "key", "open"), "invalid_arguments": (),
    "backend_unavailable": ("observe", "shell"), "execution_error": ("observe", "key", "open", "shell"),
    "error": ("observe", "key", "open", "shell"), "permission": ("observe",), "denied": ("observe",),
}
ACTION_FALLBACKS = {
    "click": ("observe", "select", "key", "open"), "select": ("observe", "click", "key", "open"),
    "type": ("observe", "open", "key"), "key": ("observe", "click", "type", "open"),
    "scroll": ("observe", "click", "key"), "drag": ("observe", "click", "select", "key"),
    "open": ("observe", "key", "shell"), "close": ("observe", "key", "shell"),
    "shell": ("observe", "find", "read", "open"), "write": ("read", "find", "shell", "observe"),
    "create": ("find", "read", "shell", "observe"), "move": ("find", "read", "shell", "observe"),
    "copy": ("find", "read", "shell", "observe"), "rename": ("find", "read", "shell", "observe"),
    "delete": ("find", "read", "shell", "observe"),
}
CORRECTABLE_ERRORS = {"invalid_arguments", "target_required"}


def _merged_fallbacks(action, error):
    merged = []
    for candidates in (ERROR_FALLBACKS.get(error, ()), ACTION_FALLBACKS.get(action, ())):
        for tool in candidates:
            if tool and tool != action and tool not in merged:
                merged.append(tool)
    return merged or ["observe"]


def _failure_output(result):
    value = result.get("output")
    if value in (None, ""):
        value = result.get("data")
    return str(value or "").strip()[:1200]


def classify_failure(action, result):
    """Classify a failed tool result and produce recovery guidance."""
    action = str(action or "").strip()
    result = result if isinstance(result, dict) else {}
    if result.get("success") is True:
        return {"failed": False, "action": action, "error": None, "reason": "", "output": "", "fallback_tools": [], "avoid_same_action": False, "force_observe": False}
    error = str(result.get("error") or "").strip()
    output = _failure_output(result)
    fallback = _merged_fallbacks(action, error)
    if error in CORRECTABLE_ERRORS:
        return {"failed": True, "action": action, "error": error, "reason": "The capability was not proven unusable. Correct the arguments or provide the missing target, then retry the same action if appropriate.", "output": output, "fallback_tools": fallback, "avoid_same_action": False, "force_observe": error == "target_required"}
    if error in {"out_of_bounds", "invalid_coordinate", "target_not_frontmost", "activate_failed"}:
        reason = "GUI state is stale or inconsistent. Refresh observation before choosing another action."
    elif error in {"backend_unavailable", "execution_error", "error"}:
        reason = "The current execution route failed. Choose another universal capability instead of repeating it."
    elif error in {"denied", "permission"}:
        reason = "The action is governed by permissions. Do not blindly retry the same action."
    else:
        reason = "The requested route failed. Use the failure as evidence and choose a different route."
    return {"failed": True, "action": action, "error": error, "reason": reason, "output": output, "fallback_tools": fallback, "avoid_same_action": True, "force_observe": True}


def recovery_tools(action, result):
    return classify_failure(action, result)["fallback_tools"]


def should_force_observe(action, result):
    return bool(classify_failure(action, result).get("force_observe"))


def recovery_context(action, result):
    return classify_failure(action, result)
