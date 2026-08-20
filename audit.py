"""Журнал выполнения инструментов (audit trail).

Записи пишутся в JSON Lines. Журнал никогда не должен ломать
основной поток: любые ошибки записи игнорируются.
"""

import json
import os
import threading
from collections.abc import Mapping
from datetime import datetime

from config import LOG_DIR

AUDIT_FILE = str(LOG_DIR / "tool_audit.jsonl")
SENSITIVE_ARG_KEYS = ("token", "secret", "password", "api_key", "apikey", "authorization", "auth")
MAX_ARG_VALUE_LENGTH = 200
MAX_OUTPUT_LENGTH = 500
TOOL_SENSITIVE_ARG_KEYS = {"type": ("text",)}
_lock = threading.Lock()
_activity_hook = None


def set_activity_hook(hook):
    global _activity_hook
    _activity_hook = hook


def clear_activity_hook():
    global _activity_hook
    _activity_hook = None


def _sensitive(key, sensitive):
    return any(part in str(key).lower() for part in sensitive)


def _json_safe(value, sensitive, depth=0):
    if depth > 8:
        return "<truncated>"
    if isinstance(value, Mapping):
        return {str(key): "***" if _sensitive(key, sensitive) else _json_safe(item, sensitive, depth + 1) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item, sensitive, depth + 1) for item in value]
    if isinstance(value, str):
        return value[:MAX_ARG_VALUE_LENGTH] + "..." if len(value) > MAX_ARG_VALUE_LENGTH else value
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def _safe_arguments(arguments, tool_name=None):
    sensitive = set(SENSITIVE_ARG_KEYS)
    sensitive.update(TOOL_SENSITIVE_ARG_KEYS.get(tool_name or "", ()))
    if not isinstance(arguments, Mapping):
        return {"value": _json_safe(arguments, sensitive)}
    return _json_safe(arguments, sensitive)


def _truncate(value):
    if not isinstance(value, str):
        return value
    return value[:MAX_OUTPUT_LENGTH] + "..." if len(value) > MAX_OUTPUT_LENGTH else value


def _result_output(result):
    if not isinstance(result, Mapping):
        return "" if result is None else str(result)
    output = result.get("output")
    if output is not None:
        return output
    data = result.get("data")
    if data is None:
        return ""
    try:
        return json.dumps(data, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(data)


def _write_json_line(entry):
    with _lock:
        os.makedirs(os.path.dirname(AUDIT_FILE), exist_ok=True)
        with open(AUDIT_FILE, "a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def record_tool_execution(tool_name, arguments, result, permission_decision, source=None, task_id=None, step=None, action=None):
    """Записывает выполнение инструмента в журнал (best-effort)."""
    try:
        hook = _activity_hook
        if hook is not None:
            try:
                hook(tool_name, arguments)
            except Exception:
                pass
        result_map = result if isinstance(result, Mapping) else {}
        entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "tool": str(tool_name),
            "arguments": _safe_arguments(arguments, tool_name),
            "success": bool(result_map.get("success")),
            "error": result_map.get("error") if result_map else ("error" if result is None else None),
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
