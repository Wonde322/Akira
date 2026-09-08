from collections import OrderedDict

import json

import config
from audit import record_tool_execution
from capabilities.observation import (
    build_observation,
    observation_to_message,
    prune_observation_history,
)
from capabilities.protocol import is_structured, result_to_text
from capabilities.recovery import (
    classify_failure,
    should_force_observe,
)
from capabilities.tool_router import select_tool_schemas
from config import (
    COMPUTER_USE_MAX_STEPS,
    COMPUTER_USE_TOOLS,
    MAX_ACTIONS_WITHOUT_OBSERVE,
    MAX_HISTORY,
    MAX_TOOL_ITERATIONS,
    MAX_TURN_PERSISTED,
    MODEL,
    NO_PROGRESS_LIMIT,
    REASONING_VISION,
    STATE_CHANGING_TOOLS,
)
from memory import build_memory_context
from permissions import get_permission, request_confirmation
from session import Session
from tool_registry import get_tool_implementation, get_tool_schemas
from capability_layer import resolve_capability


client = None


def _ensure_client():
    global client

    if config._client is None:
        config.create_groq_client()

    client = config._client
    return client


SYSTEM_PROMPT = """
Ты — Акира, персональный ассистент пользователя.

Обращайся к себе в мужском роде.
Отвечай на русском языке.
Будь кратким и естественным.

Ты работаешь как компьютерный агент. Не придумывай выполненные действия: если запрос требует действия, используй доступный инструмент и сообщи результат. Если инструмент вернул ошибку, честно сообщи её и попробуй восстановление, если это безопасно.

Для обычного разговора не вызывай инструменты без необходимости. Для действий на компьютере предпочитай конкретные зарегистрированные capability-инструменты. Не используй shell как обходной путь, если есть специализированный безопасный capability.
"""

COMPUTER_USE_SYSTEM_PROMPT = SYSTEM_PROMPT

ALL_TOOLS = get_tool_schemas()


def get_session(session_id=None):
    return Session.get(session_id)


def _execute(function_name, arguments):
    permission = get_permission(function_name)
    if permission == "blocked":
        result = {
            "success": False,
            "error": "blocked",
            "output": "Инструмент заблокирован настройками разрешений.",
        }
        return result, permission

    if permission == "confirm":
        if not request_confirmation(function_name, arguments):
            result = {
                "success": False,
                "error": "denied",
                "output": "Пользователь не разрешил выполнение действия.",
            }
            return result, "denied"
        decision = "confirmed"
    else:
        decision = permission

    implementation = get_tool_implementation(function_name)
    resolved_name = function_name
    if implementation is None:
        capability = resolve_capability(function_name)
        if capability and capability.get("implementation"):
            implementation = capability["implementation"]
            resolved_name = capability.get("name", function_name)

    if implementation is None:
        return {
            "success": False,
            "error": "unknown",
            "output": "Неизвестный инструмент.",
        }, decision

    try:
        output = implementation(**arguments)
    except Exception as exc:
        output = {
            "success": False,
            "error": "error",
            "output": f"Ошибка выполнения инструмента: {exc}",
        }

    if is_structured(output):
        result = dict(output)
    else:
        result = {"success": True, "error": None, "output": str(output)}

    result.setdefault("success", result.get("error") is None)
    result.setdefault("error", None)
    result["requested_tool"] = function_name
    result["resolved_tool"] = resolved_name

    record_tool_execution(function_name, arguments, result, decision)
    return result, decision


def ask(message, session_id=None):
    # Canonical reasoning/execution loop lives here. The implementation below is
    # intentionally kept as the single owner of model turns and tool iterations.
    session = get_session(session_id)
    history = session.history[-MAX_HISTORY:]
    current_message = str(message).strip()
    if not current_message:
        return ""

    client_instance = _ensure_client()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history]
    messages.append({"role": "user", "content": current_message})

    for _ in range(MAX_TOOL_ITERATIONS):
        response = client_instance.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=ALL_TOOLS,
            tool_choice="auto",
        )
        choice = response.choices[0]
        message_obj = choice.message
        tool_calls = getattr(message_obj, "tool_calls", None) or []

        if not tool_calls:
            answer = getattr(message_obj, "content", None) or "Готово."
            session.add("user", current_message)
            session.add("assistant", answer)
            return answer

        messages.append(message_obj)
        for tool_call in tool_calls:
            name = tool_call.function.name
            try:
                arguments = json.loads(tool_call.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}
            result, _ = _execute(name, arguments)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": name,
                "content": result_to_text(result),
            })

    return "Не удалось завершить действие за отведённое число шагов."
