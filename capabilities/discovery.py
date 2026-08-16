"""Dynamic capability discovery for Akira.

This is deliberately independent from the execution engine.

The tool can search the COMPLETE registry even when the normal relevance
router has hidden some capabilities from the current reasoning call.
"""

import re


_STOPWORDS = {
    "и", "или", "а", "но", "что", "это", "как", "мне", "ты", "я",
    "в", "на", "из", "по", "для", "с", "со", "у", "к", "от", "до",
    "the", "a", "an", "and", "or", "to", "of", "for", "in", "on",
    "with", "is", "it", "my", "me",
}


_ALIASES = {
    "браузер": {"browser", "open", "web"},
    "интернет": {"browser", "web", "url", "open"},
    "сайт": {"browser", "web", "url", "open"},
    "видео": {"video", "youtube", "media"},
    "музыка": {"music", "spotify", "audio", "media"},
    "звук": {"audio", "volume", "sound"},
    "громкость": {"volume", "audio", "sound"},
    "экран": {"observe", "screen", "vision"},
    "мышь": {"click", "select", "drag", "scroll"},
    "клавиатура": {"key", "type"},
    "текст": {"type", "write", "read"},
    "файл": {"file", "filesystem", "read", "write", "create"},
    "папка": {"directory", "filesystem", "find", "create"},
    "терминал": {"shell", "command", "terminal"},
    "команда": {"shell", "command", "execute"},
    "память": {"memory", "remember", "recall"},
    "задача": {"task", "plan"},
    "план": {"task", "plan"},
}


def _tokens(text):
    raw = re.findall(
        r"[a-zA-Zа-яА-ЯёЁ0-9_]+",
        str(text or "").lower(),
    )

    result = set()

    for token in raw:
        if token in _STOPWORDS:
            continue

        result.add(token)
        result.update(_ALIASES.get(token, ()))

    return result


def _schema_text(schema):
    function = schema.get("function", {})

    name = function.get("name", "")
    description = function.get("description", "")

    parameters = function.get("parameters", {})
    properties = parameters.get("properties", {})

    return (
        f"{name} "
        f"{description} "
        f"{' '.join(properties.keys())}"
    )


def _score(query, schema):
    query_tokens = _tokens(query)
    tool_tokens = _tokens(_schema_text(schema))

    if not query_tokens or not tool_tokens:
        return 0

    overlap = query_tokens & tool_tokens

    if not overlap:
        return 0

    score = len(overlap)

    name = schema.get("function", {}).get("name", "")
    name_tokens = _tokens(name)

    score += len(query_tokens & name_tokens) * 4

    return score


def discover_capability(query, limit=8):
    """Ищет нужные capabilities во всём registry."""

    from tool_registry import get_tool_schemas

    schemas = get_tool_schemas()

    scored = []

    for schema in schemas:
        name = schema.get("function", {}).get("name", "")

        if name == "discover_capability":
            continue

        score = _score(query, schema)

        if score > 0:
            scored.append((score, name, schema))

    scored.sort(
        key=lambda item: (-item[0], item[1])
    )

    limit = max(1, min(int(limit or 8), 12))

    selected = scored[:limit]

    return {
        "success": True,
        "data": {
            "query": str(query or ""),
            "tools": [
                {
                    "name": name,
                    "score": score,
                    "description": schema["function"].get(
                        "description", ""
                    ),
                }
                for score, name, schema in selected
            ],
            "count": len(selected),
        },
        "output": (
            "Найдено capabilities: "
            + ", ".join(name for _, name, _ in selected)
            if selected
            else "Подходящие capabilities не найдены."
        ),
    }
