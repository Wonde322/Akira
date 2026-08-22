"""Shared result protocol for Akira capabilities."""

import json


def ok(data=None, **metadata):
    return {"success": True, "data": data, "error": None, "metadata": metadata}


def fail(error, detail=None, **metadata):
    return {"success": False, "data": detail, "error": str(error), "metadata": metadata}


def is_structured(result):
    """Return True only for values that satisfy the capability result shape."""
    return (
        isinstance(result, dict)
        and isinstance(result.get("success"), bool)
        and "data" in result
        and "error" in result
        and isinstance(result.get("metadata", {}), dict)
    )


def data_to_text(data, limit=None):
    if data is None:
        return ""
    if isinstance(data, str):
        text = data
    elif isinstance(data, (list, dict)):
        try:
            text = json.dumps(data, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            text = str(data)
    else:
        text = str(data)
    return text if limit is None else text[:limit]


def result_to_text(result):
    """Convert structured or legacy tool output into model-readable text."""
    if not isinstance(result, dict):
        return str(result)
    if not is_structured(result):
        output = result.get("output") or ""
        if result.get("success") is True:
            return str(output)
        return "ОШИБКА (" + str(result.get("error") or "unknown_error") + "): " + str(output)
    if result["success"]:
        return data_to_text(result["data"])
    detail = result["data"]
    if detail is None:
        detail = result["metadata"].get("message")
    return "ОШИБКА (" + str(result.get("error") or "unknown_error") + "): " + data_to_text(detail)
