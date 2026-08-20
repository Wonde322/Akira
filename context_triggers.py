"""Deterministic contextual trigger matching for proactive desktop events.

This layer turns raw desktop context changes into explicit policy matches. It does
not interpret screenshots or call an LLM: a rule only fires when the observed UI
matches declared application/window criteria.
"""
from __future__ import annotations


def _text(value):
    return str(value or "").strip()


def ui_context(ui):
    """Extract a small stable app/window context from backend-specific metadata."""
    if not isinstance(ui, dict):
        return {"app": "", "title": ""}
    app = (
        ui.get("app")
        or ui.get("application")
        or ui.get("process")
        or ui.get("name")
    )
    title = ui.get("title") or ui.get("window") or ui.get("window_title")
    return {"app": _text(app), "title": _text(title)}


def changed_context(previous_ui, current_ui):
    previous = ui_context(previous_ui)
    current = ui_context(current_ui)
    return {
        "app_changed": previous["app"] != current["app"],
        "title_changed": previous["title"] != current["title"],
        "previous": previous,
        "current": current,
    }


def _matches(value, expected):
    expected = _text(expected)
    if not expected:
        return True
    return expected.casefold() in _text(value).casefold()


class ContextTriggerEngine:
    """Matches explicit context rules against a desktop.changed payload."""

    def __init__(self, rules=None):
        self._rules = []
        self.set_rules(rules or [])

    def set_rules(self, rules):
        cleaned = []
        for index, rule in enumerate(rules or []):
            if not isinstance(rule, dict):
                continue
            action = _text(rule.get("action") or "notify").lower()
            if action not in {"notify", "ask_user"}:
                continue
            rule_id = _text(rule.get("id")) or f"context-rule-{index + 1}"
            if not _text(rule.get("app")) and not _text(rule.get("title")):
                continue
            cleaned.append({
                "id": rule_id,
                "app": _text(rule.get("app")),
                "title": _text(rule.get("title")),
                "action": action,
                "message": _text(rule.get("message")),
                "on_transition": bool(rule.get("on_transition", True)),
                "priority": _text(rule.get("priority") or "normal").lower(),
            })
        self._rules = cleaned

    def rules(self):
        return [dict(rule) for rule in self._rules]

    def match(self, payload):
        payload = payload if isinstance(payload, dict) else {}
        delta = changed_context(payload.get("previous_ui"), payload.get("ui"))
        current = delta["current"]
        matches = []
        for rule in self._rules:
            if rule["on_transition"] and not (delta["app_changed"] or delta["title_changed"]):
                continue
            if not _matches(current["app"], rule["app"]):
                continue
            if not _matches(current["title"], rule["title"]):
                continue
            message = rule["message"] or (
                f"Контекст изменился: {current['app']}"
                + (f" — {current['title']}" if current["title"] else "")
            )
            matches.append({
                "rule": dict(rule),
                "message": message,
                "context": delta,
            })
        return matches
