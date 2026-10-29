"""Lightweight relevance router for Akira tools.

Routing uses tool names/descriptions and the caller's conversation context.
Ambiguity keeps the small discovery surface rather than exposing every tool.
"""
from __future__ import annotations

import math
import re
import unicodedata
from difflib import SequenceMatcher

from capability_layer import CAPABILITIES

_STOPWORDS = {
    "и", "или", "а", "но", "что", "это", "как", "мне", "ты", "я", "в", "на", "из", "по", "для", "с", "со", "у", "к", "от", "до",
    "the", "a", "an", "and", "or", "to", "of", "for", "in", "on", "with", "is", "it", "my", "me", "please",
}

_CYRILLIC_TO_LATIN = str.maketrans({
    "а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ё":"e","ж":"zh","з":"z","и":"i","й":"y",
    "к":"k","л":"l","м":"m","н":"n","о":"o","п":"p","р":"r","с":"s","т":"t","у":"u","ф":"f",
    "х":"h","ц":"c","ч":"ch","ш":"sh","щ":"sch","ъ":"","ы":"y","ь":"","э":"e","ю":"yu","я":"ya",
})

# Universal operation vocabulary, independent of any application names.
_OPERATION_STEMS = {
    "otkro": "open", "otkry": "open", "zapus": "open",
    "zakro": "close", "zakry": "close",
}


def _normalize_word(token: str) -> str:
    value = unicodedata.normalize("NFKD", token).casefold().translate(_CYRILLIC_TO_LATIN)
    return re.sub(r"[^a-z0-9]+", "", value)


def _stem(token: str) -> str:
    token = _normalize_word(token)
    if len(token) <= 4:
        return token
    return token[:5]


def _tokens(text):
    if not text:
        return set()
    result = set()
    for raw in re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9_]+", str(text).casefold()):
        if raw in _STOPWORDS:
            continue
        normalized = _normalize_word(raw)
        if not normalized:
            continue
        result.add(raw)
        result.add(normalized)
        stem = _stem(normalized)
        result.add(stem)
        operation = _OPERATION_STEMS.get(stem)
        if operation:
            result.add(operation)
    return result


def _fuzzy_overlap(query_tokens, schema_tokens):
    score = 0.0
    for query in query_tokens:
        if len(query) < 4:
            continue
        best = max((SequenceMatcher(None, query, schema).ratio() for schema in schema_tokens), default=0.0)
        if best >= 0.72:
            score += best
    return score


def _score(query, schema):
    function = schema.get("function", {}) if isinstance(schema, dict) else {}
    name = str(function.get("name", "")).lower()
    description = str(function.get("description", "")).lower()
    query_tokens = _tokens(query)
    schema_tokens = _tokens(name + " " + description)
    overlap = query_tokens & schema_tokens
    score = math.log1p(len(overlap)) if overlap else 0.0
    score += 0.35 * min(4.0, _fuzzy_overlap(query_tokens, schema_tokens))
    if name in query_tokens or _normalize_word(name) in query_tokens:
        score += 2.0

    semantic_tokens = set()
    for capability in CAPABILITIES:
        try:
            if capability.tool.casefold() == name:
                semantic_tokens.update(_tokens(capability.operation))
                semantic_tokens.update(_tokens(capability.name))
        except Exception:
            continue
    semantic_overlap = query_tokens & semantic_tokens
    if semantic_overlap:
        score += 0.75 * math.log1p(len(semantic_overlap))
    return score


def is_web_query(query):
    return bool(re.search(
        r"погугл|гугл|загугл|интернет|поиск.{0,24}(?:сети|веб|web)|найди.{0,24}(?:сети|сайт)|\b(?:google|search|web|browse)\b",
        str(query or "").casefold(),
    ))


def _always_include(task_active):
    base = {"discover_capability"}
    if task_active:
        base.update({"finish_task", "verify_goal", "observe", "plan_task", "update_task_plan", "complete_plan_step", "fail_plan_step"})
    return base


def select_tool_schemas(query, schemas, limit=12, task_active=False, pinned_tools=None):
    if not schemas:
        return []
    scored = []
    for schema in schemas:
        name = schema.get("function", {}).get("name", "")
        scored.append((_score(query, schema), name, schema))
    scored.sort(key=lambda item: (-item[0], item[1]))

    mandatory = _always_include(task_active)
    if is_web_query(query):
        mandatory.add("web_search")
    if pinned_tools:
        mandatory.update(str(name) for name in pinned_tools if name)

    selected = []
    selected_names = set()
    for _, name, schema in scored:
        if name in mandatory:
            selected.append(schema)
            selected_names.add(name)

    remaining = max(0, limit - len(selected))
    for score, name, schema in scored:
        if name in selected_names or remaining <= 0:
            continue
        if score <= 0:
            continue
        selected.append(schema)
        selected_names.add(name)
        remaining -= 1

    return selected


def explain_selection(query, schemas, limit=12, task_active=False, pinned_tools=None):
    selected = select_tool_schemas(query, schemas, limit=limit, task_active=task_active, pinned_tools=pinned_tools)
    return {
        "query": query,
        "selected": [schema.get("function", {}).get("name") for schema in selected],
        "count": len(selected),
        "total": len(schemas),
    }
