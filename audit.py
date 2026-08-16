"""Журнал выполнения инструментов (audit trail).

Записи пишутся в JSON Lines. Журнал никогда не должен ломать
основной поток: любые ошибки записи игнорируются.
"""

import json
import os
import threading
from datetime import datetime

from config import LOG_DIR


AUDIT_FILE = str(LOG_DIR / "tool_audit.jsonl")

SENSITIVE_ARG_KEYS = (
    "token",
    "secret",
    "password",
    "api_key",
    "apikey",
    "authorization",
    "auth",
)

MAX_ARG_VALUE_LENGTH = 200
MAX_OUTPUT_LENGTH = 500

# Дополнительные чувствительные аргументы для конкретных инструментов.
# Например, type(text="пароль") не должен сохранять пароль в логах.
TOOL_SENSITIVE_ARG_KEYS = {
    "type": ("text",),
}

_lock = threading.Lock()

# Опциональный хук для UI-слоёв: вызывается с (tool_name, arguments)
# перед записью записи. По умолчанию отключён и никогда не ломает журнал.
_activity_hook = None


def set_activity_hook(hook):
    """Устанавливает callback(tool_name, arguments), вызываемый при записи."""
    global _activity_hook
    _activity_hook = hook


def clear_activity_hook():
    global _activity_hook
    _activity_hook = None


def _safe_arguments(arguments, tool_name=None):
    """Возвращает копию аргументов без секретов и гигантских значений."""
    sensitive = set(SENSITIVE_ARG_KEYS)

    for key in TOOL_SENSITIVE_ARG_KEYS.get(tool_name or "", ()):
        sensitive.add(key)

    safe = {}

    for key, value in (arguments or {}).items():
        if any(part in str(key).lower() for part in sensitive):
            safe[key] = "***"
            continue

        if isinstance(value, str) and len(value) > MAX_ARG_VALUE_LENGTH:
            safe[key] = value[:MAX_ARG_VALUE_LENGTH] + "..."

        else:
            safe[key] = value

    return safe


def _truncate(value):
    if not isinstance(value, str):
        return value

    if len(value) > MAX_OUTPUT_LENGTH:
        return value[:MAX_OUTPUT_LENGTH] + "..."

    return value


def _result_output(result):
    """Извлекает текст результата: output для legacy, data для протокола."""
    if not result:
        return ""

    output = result.get("output")

    if output is not None:
        return output

    data = result.get("data")

    if data is None:
        return ""

    try:
        return json.dumps(data, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(data)


def _write_json_line(entry):
    with _lock:
        os.makedirs(os.path.dirname(AUDIT_FILE), exist_ok=True)

        with open(AUDIT_FILE, "a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")


def record_tool_execution(
    tool_name,
    arguments,
    result,
    permission_decision,
    source=None,
    task_id=None,
    step=None,
    action=None,
):
    """Записывает выполнение инструмента в журнал (best-effort)."""
    try:
        hook = _activity_hook

        if hook is not None:
            try:
                hook(tool_name, arguments)
            except Exception:
                pass

        entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "tool": tool_name,
            "arguments": _safe_arguments(arguments, tool_name),
            "success": bool(result.get("success")) if result else False,
            "error": result.get("error") if result else "error",
            "output": _truncate(_result_output(result)),
            "permission": permission_decision,
            "source": source,
            "task_id": task_id,
            "step": step,
            "action": action,
        }

        _write_json_line(entry)

    except Exception:
        pass