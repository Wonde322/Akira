"""Единый протокол результатов capability-инструментов.

Формат результата:
    {"success": bool, "data": ..., "error": str|None, "metadata": {...}}

- success True: операция выполнена, data содержит полезные данные.
- success False: операция не выполнена, error — машинный код ошибки,
  data (detail) — человекочитаемое описание.
- metadata: дополнительные сведения, не обязательные для показа модели.

Протокол не зависит от внешних модулей проекта и может использоваться
и brain, и audit, и самими capabilities.
"""

import json


def ok(data=None, **metadata):
    """Структурированный успешный результат."""
    return {
        "success": True,
        "data": data,
        "error": None,
        "metadata": metadata,
    }


def fail(error, detail=None, **metadata):
    """Структурированный результат ошибки."""
    return {
        "success": False,
        "data": detail,
        "error": error,
        "metadata": metadata,
    }


def is_structured(result):
    """Проверяет, что результат следует протоколу capabilities."""
    return isinstance(result, dict) and "success" in result and "data" in result


def data_to_text(data, limit=None):
    """Превращает data в удобный для модели текст."""
    if data is None:
        return ""

    if isinstance(data, str):
        return data if limit is None else data[:limit]

    if isinstance(data, (list, dict)):
        try:
            text = json.dumps(data, ensure_ascii=False)
        except (TypeError, ValueError):
            text = str(data)
    else:
        text = str(data)

    return text if limit is None else text[:limit]


def result_to_text(result):
    """Превращает любой результат (structured или legacy) в текст для модели."""
    if not isinstance(result, dict):
        return str(result)

    if not is_structured(result):
        output = result.get("output") or ""

        if result.get("success"):
            return str(output)

        return "ОШИБКА (" + str(result.get("error")) + "): " + str(output)

    if result.get("success"):
        return data_to_text(result.get("data"))

    detail = result.get("data")

    if detail is None:
        detail = result.get("metadata", {}).get("message")

    return "ОШИБКА (" + str(result.get("error")) + "): " + data_to_text(detail)
