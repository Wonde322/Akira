"""Persistent storage and management for contextual proactive rules."""
from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_RULES_FILE = ROOT / "runtime" / "context_rules.json"


def _text(value):
    return str(value or "").strip()


class ContextRuleStore:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else DEFAULT_RULES_FILE
        self._lock = threading.RLock()
        self._rules = []
        self._load()

    def _load(self):
        with self._lock:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                return
            rules = data.get("rules") if isinstance(data, dict) else None
            if isinstance(rules, list):
                self._rules = [dict(rule) for rule in rules if isinstance(rule, dict)]

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps({"rules": self._rules}, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    @staticmethod
    def _normalize(rule, existing_id=None):
        rule = rule if isinstance(rule, dict) else {}
        action = _text(rule.get("action") or "notify").lower()
        if action not in {"notify", "ask_user"}:
            raise ValueError("unsupported_context_rule_action")
        app = _text(rule.get("app"))
        title = _text(rule.get("title"))
        if not app and not title:
            raise ValueError("context_rule_requires_app_or_title")
        message = _text(rule.get("message"))
        if not message:
            raise ValueError("context_rule_requires_message")
        priority = _text(rule.get("priority") or "normal").lower()
        if priority not in {"low", "normal", "high"}:
            priority = "normal"
        return {
            "id": existing_id or _text(rule.get("id")) or uuid.uuid4().hex[:12],
            "app": app,
            "title": title,
            "action": action,
            "message": message,
            "on_transition": bool(rule.get("on_transition", True)),
            "priority": priority,
            "enabled": bool(rule.get("enabled", True)),
        }

    def list(self):
        with self._lock:
            return [dict(rule) for rule in self._rules]

    def active(self):
        with self._lock:
            return [dict(rule) for rule in self._rules if rule.get("enabled", True)]

    def add(self, rule):
        normalized = self._normalize(rule)
        with self._lock:
            while any(item.get("id") == normalized["id"] for item in self._rules):
                normalized["id"] = uuid.uuid4().hex[:12]
            self._rules.append(normalized)
            self._save()
            return dict(normalized)

    def remove(self, rule_id):
        rule_id = _text(rule_id)
        with self._lock:
            before = len(self._rules)
            self._rules = [rule for rule in self._rules if rule.get("id") != rule_id]
            removed = len(self._rules) != before
            if removed:
                self._save()
            return removed

    def set_enabled(self, rule_id, enabled):
        rule_id = _text(rule_id)
        with self._lock:
            for rule in self._rules:
                if rule.get("id") == rule_id:
                    rule["enabled"] = bool(enabled)
                    self._save()
                    return dict(rule)
        return None


_store = None
_store_lock = threading.Lock()


def get_context_rule_store():
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = ContextRuleStore()
    return _store
