"""Execution primitives for Akira's agent loop.

This module owns tool resolution, permission checks, phase guards and audit
recording. Reasoning/session orchestration can therefore evolve independently
from concrete capability execution.
"""
from __future__ import annotations

from audit import record_tool_execution
from capabilities.protocol import is_structured
from capability_layer import resolve_capability
from permissions import get_permission, request_confirmation
from tool_registry import get_tool_implementation


def tool_result(success, error, output):
    return {"success": success, "error": error, "output": output}


def execute(function_name, arguments):
    function = get_tool_implementation(function_name)
    resolved_name = function_name
    capability_resolution = None

    if function is None:
        capability_resolution = resolve_capability(function_name)
        if capability_resolution.get("success"):
            resolved_name = capability_resolution["tool"]
            function = get_tool_implementation(resolved_name)

    permission = get_permission(resolved_name)
    if permission == "blocked":
        return tool_result(False, "blocked", "Инструмент заблокирован настройками разрешений."), "blocked"

    if permission == "confirm":
        if not request_confirmation(resolved_name, arguments):
            return tool_result(False, "denied", "Пользователь не разрешил выполнение действия."), "denied"
        decision = "confirmed"
    else:
        decision = "auto"

    if function is None:
        return tool_result(False, "unknown", "Неизвестный инструмент."), decision

    try:
        output = function(**arguments)
    except Exception as error:
        return tool_result(False, "error", "Ошибка выполнения инструмента: " + str(error)), decision

    if is_structured(output):
        return output, decision

    result = tool_result(True, None, output)
    result.setdefault("requested_tool", function_name)
    result.setdefault("resolved_tool", resolved_name)
    if capability_resolution is not None:
        result.setdefault("capability", capability_resolution.get("capability"))
        result.setdefault("capability_modality", capability_resolution.get("modality"))
    return result, decision


def task_kwargs(session, action):
    if session is None or session.task is None:
        return {}
    return {
        "task_id": str(session.task.get("started_at")),
        "step": session.task.get("step"),
        "action": action,
    }


def phase_allows_tool(session, function_name, computer_use_tools):
    if session is None or session.task is None:
        return True, None
    phase = session.task.get("phase", "planning")
    if session.recovery_requires_different_action(function_name):
        return False, f"Recovery forbids repeating failed action '{function_name}'. Choose another capability."
    if session.recovery_needs_observation() and function_name != "observe":
        return False, "Recovery requires a fresh observe before another action."

    common = {"observe", "discover_capability", "plan_task", "update_task_plan"}
    computer_actions = set(computer_use_tools) - {"observe", "verify_goal", "finish_task"}
    allowed = {
        "planning": common,
        "observing": {"observe"},
        "acting": common | computer_actions | {"verify_goal", "finish_task"},
        "verifying": {"observe", "verify_goal"},
        "recovering": common | computer_actions | {"verify_goal"},
        "done": set(), "failed": set(), "permission": set(),
    }
    if function_name in allowed.get(phase, set()):
        return True, None
    return False, f"Tool '{function_name}' запрещён в phase='{phase}'. Сначала переведи задачу в подходящую фазу."


def execute_and_audit(function_name, arguments, *, source=None, session=None, computer_use_tools=()):
    allowed, reason = phase_allows_tool(session, function_name, computer_use_tools)
    if not allowed:
        result = tool_result(False, "phase_tool_blocked", reason)
        record_tool_execution(function_name, arguments, result, "blocked_by_phase", source=source, **task_kwargs(session, function_name))
        return result

    result, decision = execute(function_name, arguments)
    record_tool_execution(function_name, arguments, result, decision, source=source, **task_kwargs(session, function_name))
    return result
