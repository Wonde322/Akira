"""Explicit controls for Akira's proactive interruption mode."""

from proactive_interruption_control import get_proactive_interruption_control
from tool_registry import ToolDefinition


def set_proactive_mode(mode, duration_seconds=None):
    try:
        state = get_proactive_interruption_control().set_mode(mode, duration_seconds)
        return {"success": True, "state": state}
    except (TypeError, ValueError) as error:
        return {"success": False, "error": str(error)}


def get_proactive_mode():
    state = get_proactive_interruption_control().snapshot()
    return {"success": True, "state": state}


def reset_proactive_mode():
    state = get_proactive_interruption_control().reset()
    return {"success": True, "state": state}


def _params(properties, required=None):
    result = {"type": "object", "properties": properties}
    if required:
        result["required"] = required
    return result


TOOLS = (
    ToolDefinition(
        name="set_proactive_mode",
        description="Меняет режим вмешательств Акиры: normal — обычный, focus — только ненавязчивые low-priority уведомления и важное, quiet — не отвлекать до отключения или истечения таймера.",
        parameters=_params({
            "mode": {"type": "string", "enum": ["normal", "focus", "quiet"]},
            "duration_seconds": {"type": "number", "description": "Необязательная длительность quiet-режима в секундах."},
        }, ["mode"]),
        implementation_module="skills.proactive_control.skill",
        implementation_name="set_proactive_mode",
        permission_policy="auto",
    ),
    ToolDefinition(
        name="get_proactive_mode",
        description="Показывает текущий режим proactive-вмешательств Акиры и время окончания quiet-режима, если оно задано.",
        parameters=_params({}),
        implementation_module="skills.proactive_control.skill",
        implementation_name="get_proactive_mode",
        permission_policy="auto",
    ),
    ToolDefinition(
        name="reset_proactive_mode",
        description="Возвращает proactive-вмешательства Акиры в обычный режим.",
        parameters=_params({}),
        implementation_module="skills.proactive_control.skill",
        implementation_name="reset_proactive_mode",
        permission_policy="auto",
    ),
)
