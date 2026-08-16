"""Lightweight relevance router for Akira tools.

No external dependencies.

The router ranks tool schemas using:
- normalized lexical overlap;
- Russian/English aliases;
- tool-name matches;
- parameter-name matches;
- intent groups;
- mandatory execution tools.

It is deliberately conservative:
if confidence is low, it returns a wider tool set instead of risking
hiding the capability the agent needs.
"""

import math
import re


# ------------------------------------------------------------
# Normalization
# ------------------------------------------------------------

_STOPWORDS = {
    "и", "или", "а", "но", "что", "это", "как", "мне", "ты", "я",
    "в", "на", "из", "по", "для", "с", "со", "у", "к", "от", "до",
    "the", "a", "an", "and", "or", "to", "of", "for", "in", "on",
    "with", "is", "it", "my", "me", "please",
}


ALIASES = {
    "открой": {"open", "launch", "app", "url"},
    "открыть": {"open", "launch", "app", "url"},
    "запусти": {"open", "launch", "app"},
    "запустить": {"open", "launch", "app"},
    "закрой": {"close", "quit", "app"},
    "закрыть": {"close", "quit", "app"},
    "найди": {"find", "search"},
    "найти": {"find", "search"},
    "поиск": {"find", "search"},
    "файл": {"file", "filesystem", "read", "write", "create"},
    "файлы": {"file", "filesystem", "read", "write", "create"},
    "прочитай": {"read", "file"},
    "прочитать": {"read", "file"},
    "запиши": {"write", "file"},
    "записать": {"write", "file"},
    "создай": {"create", "write", "file"},
    "создать": {"create", "write", "file"},
    "перемести": {"move", "file"},
    "переместить": {"move", "file"},
    "скопируй": {"copy", "file"},
    "скопировать": {"copy", "file"},
    "переименуй": {"rename", "file"},
    "переименовать": {"rename", "file"},
    "удали": {"delete", "file"},
    "удалить": {"delete", "file"},
    "терминал": {"shell", "command", "terminal"},
    "команда": {"shell", "command", "terminal"},
    "выполни": {"shell", "execute", "command"},
    "запусти": {"shell", "execute", "command", "open"},
    "экран": {"observe", "screen", "vision"},
    "посмотри": {"observe", "screen", "vision"},
    "посмотреть": {"observe", "screen", "vision"},
    "скрин": {"observe", "screen", "vision"},
    "кликни": {"click", "select", "gui"},
    "клик": {"click", "select", "gui"},
    "нажми": {"click", "key", "gui"},
    "нажать": {"click", "key", "gui"},
    "напиши": {"type", "text", "gui"},
    "введи": {"type", "text", "gui"},
    "ввести": {"type", "text", "gui"},
    "напечатай": {"type", "text", "gui"},
    "перетащи": {"drag", "gui"},
    "перетащить": {"drag", "gui"},
    "прокрути": {"scroll", "gui"},
    "прокрутить": {"scroll", "gui"},
    "подожди": {"wait"},
    "подождать": {"wait"},
    "ютуб": {"youtube", "video", "browser", "open"},
    "youtube": {"youtube", "video", "browser", "open"},
    "спотифай": {"spotify", "music", "browser", "open"},
    "spotify": {"spotify", "music", "browser", "open"},
    "музыка": {"spotify", "music", "audio"},
    "музыку": {"spotify", "music", "audio"},
    "память": {"memory", "remember"},
    "запомни": {"memory", "remember"},
    "вспомни": {"memory", "recall"},
    "задача": {"task", "plan"},
    "задачу": {"task", "plan"},
    "план": {"plan", "task"},
    "спланируй": {"plan", "task"},
    "сделай": {"task", "plan", "execute"},
}


def _tokens(text):
    if not text:
        return set()

    raw = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9_]+", str(text).lower())
    result = set()

    for token in raw:
        if token in _STOPWORDS:
            continue

        result.add(token)

        for alias in ALIASES.get(token, ()):
            result.add(alias)

    return result


def _schema_text(schema):
    function = schema.get("function", {})
    name = function.get("name", "")
    description = function.get("description", "")
    parameters = function.get("parameters", {})

    properties = parameters.get("properties", {})

    parameter_names = " ".join(properties.keys())

    return f"{name} {description} {parameter_names}"


# ------------------------------------------------------------
# Intent groups
# ------------------------------------------------------------

GROUPS = {
    "computer": {
        "open", "close", "observe", "screen_size", "click", "select",
        "type", "key", "scroll", "drag", "wait",
    },
    "filesystem": {
        "find", "read", "write", "create", "move", "copy", "rename", "delete",
    },
    "execution": {
        "shell",
    },
    "planning": {
        "plan_task", "update_task_plan",
        "complete_plan_step", "fail_plan_step", "finish_task",
    },
    "media": {
        "open_youtube", "play_spotify",
    },
    "memory": {
        "remember", "recall", "add_task", "complete_task",
        "add_event", "get_recent_events", "analyze_period",
    },
}


def _group_hits(query_tokens, tool_name):
    hits = 0

    for group in GROUPS.values():
        if tool_name not in group:
            continue

        group_tokens = set()

        for item in group:
            group_tokens.update(_tokens(item))

        hits += len(query_tokens & group_tokens)

    return hits


def _score(query, schema):
    function = schema.get("function", {})
    name = str(function.get("name", ""))

    query_tokens = _tokens(query)
    tool_tokens = _tokens(_schema_text(schema))

    if not query_tokens or not tool_tokens:
        return 0.0

    overlap = query_tokens & tool_tokens

    # Base lexical relevance.
    score = len(overlap) * 1.0

    # Exact tool-name token matches are much stronger.
    name_tokens = _tokens(name)
    score += len(query_tokens & name_tokens) * 4.0

    # Group relevance gives universal tools a boost.
    score += _group_hits(query_tokens, name) * 0.75

    # Slightly reward longer overlap because descriptions are richer.
    if overlap:
        score += math.log1p(len(overlap))

    return score


def _always_include(task_active):
    base = {
        "finish_task",
    }

    if task_active:
        base.update({
            "observe",
            "plan_task",
            "update_task_plan",
            "complete_plan_step",
            "fail_plan_step",
        })

    return base


def select_tool_schemas(
    query,
    schemas,
    limit=12,
    task_active=False,
):
    """Return the most relevant tool schemas for the current reasoning turn."""

    if not schemas:
        return []

    scored = []

    for schema in schemas:
        name = schema.get("function", {}).get("name", "")
        score = _score(query, schema)

        scored.append((score, name, schema))

    scored.sort(key=lambda item: (-item[0], item[1]))

    mandatory = _always_include(task_active)

    selected = []
    selected_names = set()

    # Always preserve mandatory execution primitives.
    for _, name, schema in scored:
        if name in mandatory:
            selected.append(schema)
            selected_names.add(name)

    # Add highest scoring tools.
    for score, name, schema in scored:
        if name in selected_names:
            continue

        if len(selected) >= limit:
            break

        selected.append(schema)
        selected_names.add(name)

    # Conservative fallback:
    # if relevance is extremely weak, don't risk hiding the actual tool.
    useful_scores = [
        score for score, _, _ in scored
        if score > 0
    ]

    if not useful_scores:
        return list(schemas)

    if max(useful_scores) < 1.0:
        return list(schemas)

    return selected


def explain_selection(query, schemas, limit=12, task_active=False):
    """Diagnostic representation useful for audit/debugging."""
    selected = select_tool_schemas(
        query,
        schemas,
        limit=limit,
        task_active=task_active,
    )

    selected_names = [
        schema.get("function", {}).get("name")
        for schema in selected
    ]

    return {
        "query": query,
        "selected": selected_names,
        "count": len(selected_names),
        "total": len(schemas),
    }
