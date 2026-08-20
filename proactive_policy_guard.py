"""Durable guardrails for proactive interruptions.

The runtime already has short-lived duplicate protection.  This guard adds a
stable policy boundary that can survive a restart and reason about equivalent
events coming from different sources.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path

_PRIORITY = {"low": 0, "normal": 1, "high": 2, "critical": 3}


class ProactivePolicyGuard:
    def __init__(self, path=None, *, cooldown_seconds=90.0, clock=None):
        self.path = Path(path) if path else None
        self.cooldown_seconds = float(cooldown_seconds)
        self.clock = clock or time.time
        self._lock = threading.RLock()
        self._entries = self._load()

    def _load(self):
        if not self.path:
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _save(self):
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(json.dumps(self._entries, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        temp.replace(self.path)

    @staticmethod
    def _priority(value):
        return _PRIORITY.get(str(value or "normal"), 1)

    @staticmethod
    def semantic_key(event, decision=None):
        payload = event.get("payload") or {}
        data = {
            "type": event.get("type"),
            "goal": payload.get("goal") or payload.get("active_task", {}).get("goal"),
            "app": payload.get("app") or payload.get("application"),
            "title": payload.get("title") or payload.get("window_title"),
            "reason": getattr(decision, "reason", None) if decision is not None else payload.get("reason"),
        }
        encoded = json.dumps(data, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def check(self, event, decision):
        """Return (allowed, reason). Higher-priority events can escalate."""
        key = self.semantic_key(event, decision)
        now = float(self.clock())
        priority = self._priority(getattr(decision, "priority", "normal"))
        with self._lock:
            previous = self._entries.get(key)
            if previous:
                age = now - float(previous.get("timestamp", 0.0))
                old_priority = int(previous.get("priority", 1))
                if age < self.cooldown_seconds and priority <= old_priority:
                    return False, "policy_cooldown"
                reason = "priority_escalation" if age < self.cooldown_seconds else "allowed"
            else:
                reason = "allowed"
            self._entries[key] = {"timestamp": now, "priority": priority}
            self._prune_locked(now)
            self._save()
        return True, reason

    def _prune_locked(self, now):
        cutoff = now - max(self.cooldown_seconds * 4, 300.0)
        self._entries = {k: v for k, v in self._entries.items() if float(v.get("timestamp", 0.0)) >= cutoff}

    def reset(self):
        with self._lock:
            self._entries = {}
            if self.path:
                try:
                    self.path.unlink()
                except FileNotFoundError:
                    pass


_guard = None
_guard_lock = threading.Lock()


def get_proactive_policy_guard():
    global _guard
    if _guard is None:
        with _guard_lock:
            if _guard is None:
                _guard = ProactivePolicyGuard("runtime/proactive_policy_guard.json")
    return _guard
