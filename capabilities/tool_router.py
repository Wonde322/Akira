from capability_layer import CAPABILITIES
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
    """Score a tool against the current reasoning query.

    Existing lexical scoring remains the primary mechanism.

    Capability semantics add a bounded boost when a concrete
    tool represents a universal operation such as:

        open
        click
        type
        observe
        read
        write
        move
        rename
        scroll
        verify
        execute

    The capability layer is the source of truth for these
    semantic relationships.
    """

    import math
    import re

    query_text = str(
        query or ""
    ).lower()

    function = (
        schema.get(
            "function",
            {}
        )
        if isinstance(
            schema,
            dict,
        )
        else {}
    )

    name = str(
        function.get(
            "name",
            "",
        )
    ).lower()

    description = str(
        function.get(
            "description",
            "",
        )
    ).lower()

    # --------------------------------------------------------
    # Existing lexical scoring.
    # --------------------------------------------------------

    # Use the router's normalized token expansion here as well.
    # This keeps Russian/English aliases effective after a task
    # becomes active and the tool set is re-ranked.
    query_tokens = _tokens(query_text)

    searchable = (
        name
        + " "
        + description
    )

    schema_tokens = _tokens(searchable)

    overlap = (
        query_tokens
        & schema_tokens
    )

    score = 0.0

    if overlap:

        score += math.log1p(
            len(overlap)
        )

    # Direct function-name match remains stronger.
    if name in query_tokens:

        score += 2.0

    # --------------------------------------------------------
    # Semantic capability scoring.
    #
    # IMPORTANT:
    # CAPABILITIES is imported from the actual universal
    # capability layer. No duplicate registry is created here.
    # --------------------------------------------------------

    semantic_terms = set()

    for capability in CAPABILITIES:

        try:

            if capability.tool.lower() != name:
                continue

            semantic_terms.add(
                capability.operation.lower()
            )

            semantic_terms.add(
                capability.name.lower()
            )

        except Exception:
            continue

    # --------------------------------------------------------
    # Capability operation can itself be multi-word in future.
    # Tokenize it rather than requiring exact phrase equality.
    # --------------------------------------------------------

    semantic_tokens = set()

    for term in semantic_terms:

        semantic_tokens.update(
            re.findall(
                r"[a-zA-Zа-яА-Я0-9_]+",
                term,
            )
        )

    semantic_overlap = (
        query_tokens
        & semantic_tokens
    )

    if semantic_overlap:

        # Bounded semantic boost.
        #
        # It is deliberately smaller than an exact tool-name
        # match, so we don't destroy existing router behaviour.
        score += 0.75 * math.log1p(
            len(semantic_overlap)
        )

    return score


def _always_include(task_active):
    base = {
        "finish_task",
        "discover_capability",
        "verify_goal",
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
    pinned_tools=None,
):
    """Return relevant tool schemas for the current reasoning turn.

    Mandatory execution primitives are always preserved.

    The remaining capacity is reserved for the most relevant
    concrete tools selected by lexical + semantic capability
    scoring.

    Therefore task-control tools cannot consume the entire
    planner tool budget.
    """

    if not schemas:
        return []

    scored = []

    for schema in schemas:

        name = (
            schema
            .get("function", {})
            .get("name", "")
        )

        score = _score(
            query,
            schema,
        )

        scored.append(
            (
                score,
                name,
                schema,
            )
        )

    scored.sort(
        key=lambda item: (
            -item[0],
            item[1],
        )
    )

    mandatory = _always_include(
        task_active
    )

    # --------------------------------------------------------
    # Discovered capabilities remain visible until task ends.
    # --------------------------------------------------------

    if pinned_tools:

        mandatory.update(
            str(name)
            for name in pinned_tools
            if name
        )

    selected = []
    selected_names = set()

    # --------------------------------------------------------
    # 1. Mandatory tools first.
    #
    # They are not allowed to consume the dynamic-tool budget.
    # --------------------------------------------------------

    for _, name, schema in scored:

        if name not in mandatory:
            continue

        selected.append(schema)
        selected_names.add(name)

    # --------------------------------------------------------
    # 2. Reserve the remaining limit for actual task tools.
    #
    # Example:
    #
    # limit = 12
    # mandatory = 8
    #
    # => 4 real task tools are still allowed.
    # --------------------------------------------------------

    remaining_slots = max(
        0,
        limit - len(selected),
    )

    # --------------------------------------------------------
    # 3. Add highest-scoring concrete tools.
    # --------------------------------------------------------

    added_dynamic = 0

    for score, name, schema in scored:

        if name in selected_names:
            continue

        if added_dynamic >= remaining_slots:
            break

        # Ignore completely irrelevant tools while there are
        # meaningful candidates available.
        if score <= 0:
            continue

        selected.append(schema)
        selected_names.add(name)
        added_dynamic += 1

    # --------------------------------------------------------
    # 4. Conservative fallback.
    #
    # If there are no useful scores at all, expose the original
    # schemas rather than hiding every tool.
    # --------------------------------------------------------

    useful_scores = [
        score
        for score, _, _ in scored
        if score > 0
    ]

    if not useful_scores:
        return list(schemas)

    # If relevance is extremely weak, preserve the old
    # conservative behaviour.
    if max(useful_scores) < 1.0:
        return list(schemas)

    return selected


def explain_selection(
    query,
    schemas,
    limit=12,
    task_active=False,
    pinned_tools=None,
):
    """Diagnostic representation useful for audit/debugging."""
    selected = select_tool_schemas(
        query,
        schemas,
        limit=limit,
        task_active=task_active,
        pinned_tools=pinned_tools,
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
