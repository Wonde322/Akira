"""User-manageable contextual proactive rules."""

from proactive_runtime import get_proactive_runtime
from tool_registry import ToolDefinition


def create_context_rule(app=None, title=None, message=None, action="notify",
                        on_transition=True, priority="normal"):
    try:
        rule = get_proactive_runtime().add_context_rule(
            app=app, title=title, message=message, action=action,
            on_transition=on_transition, priority=priority,
        )
        return {"success": True, "rule": rule,
                "output": f"Контекстное правило сохранено: {rule['id']}"}
    except ValueError as error:
        return {"success": False, "error": str(error)}


def list_context_rules():
    rules = get_proactive_runtime().context_rules()
    return {"success": True, "rules": rules, "count": len(rules)}


def remove_context_rule(rule_id):
    removed = get_proactive_runtime().remove_context_rule(rule_id)
    return {"success": removed, "removed": removed,
            "error": None if removed else "context_rule_not_found"}


def set_context_rule_enabled(rule_id, enabled):
    rule = get_proactive_runtime().set_context_rule_enabled(rule_id, enabled)
    if rule is None:
        return {"success": False, "error": "context_rule_not_found"}
    return {"success": True, "rule": rule}


def _params(properties, required=None):
    result = {"type": "object", "properties": properties}
    if required:
        result["required"] = required
    return result


TOOLS = (
    ToolDefinition(
        name="create_context_rule",
        description="Создаёт постоянное правило: когда на экране появляется указанное приложение или окно, Акира сама показывает сообщение или задаёт вопрос. Используй для запросов вида «когда я открываю Figma, напомни мне проверить сетку».",
        parameters=_params({
            "app": {"type": "string", "description": "Название приложения или его часть."},
            "title": {"type": "string", "description": "Название окна или его часть."},
            "message": {"type": "string", "description": "Что Акира должна сказать или спросить."},
            "action": {"type": "string", "enum": ["notify", "ask_user"]},
            "on_transition": {"type": "boolean", "description": "Срабатывать только при входе в контекст."},
            "priority": {"type": "string", "enum": ["low", "normal", "high"]},
        }, ["message"]),
        implementation_module="skills.context_rules.skill",
        implementation_name="create_context_rule",
        permission_policy="auto",
    ),
    ToolDefinition(
        name="list_context_rules",
        description="Показывает все сохранённые правила, по которым Акира реагирует на приложения и окна.",
        parameters=_params({}),
        implementation_module="skills.context_rules.skill",
        implementation_name="list_context_rules",
        permission_policy="auto",
    ),
    ToolDefinition(
        name="remove_context_rule",
        description="Удаляет сохранённое контекстное правило по его id.",
        parameters=_params({"rule_id": {"type": "string", "description": "ID правила."}}, ["rule_id"]),
        implementation_module="skills.context_rules.skill",
        implementation_name="remove_context_rule",
        permission_policy="auto",
    ),
    ToolDefinition(
        name="set_context_rule_enabled",
        description="Временно включает или выключает сохранённое контекстное правило.",
        parameters=_params({"rule_id": {"type": "string"}, "enabled": {"type": "boolean"}}, ["rule_id", "enabled"]),
        implementation_module="skills.context_rules.skill",
        implementation_name="set_context_rule_enabled",
        permission_policy="auto",
    ),
)
