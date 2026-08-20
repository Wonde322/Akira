"""Bound proactive interruptions with a persistent attention budget.

The budget is independent from feedback memory: feedback answers *whether this kind*
of intervention is wanted, while this layer answers *whether now is a good time* to
interrupt. Only delivered notifications/questions consume budget.
"""
from __future__ import annotations

import json
import os
import threading
import time

from proactive_interruption_control import get_proactive_interruption_control


class ProactiveAttentionBudget:
    def __init__(self, path="runtime/proactive_attention_budget.json", max_points=6,
                 refill_seconds=10 * 60, clock=None, interruption_control=None):
        self.path = path
        self.max_points = max(1.0, float(max_points))
        self.refill_seconds = max(1.0, float(refill_seconds))
        self._clock = clock or time.time
        self._interruption_control = interruption_control or get_proactive_interruption_control()
        self._lock = threading.RLock()
        self._data = self._load()

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _save(self):
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        temporary = self.path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(self._data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(temporary, self.path)

    def _refill(self, now):
        points = float(self._data.get("points", self.max_points))
        updated = float(self._data.get("updated_at", now))
        elapsed = max(0.0, now - updated)
        points = min(self.max_points, points + elapsed / self.refill_seconds)
        self._data["points"] = points
        self._data["updated_at"] = now
        return points

    @staticmethod
    def cost(action, priority):
        action = str(getattr(action, "value", action) or "")
        priority = str(priority or "normal")
        if priority == "high":
            return 0.0
        if action == "ask_user":
            return 2.0
        if action == "notify":
            return 1.0 if priority == "normal" else 0.5
        return 0.0

    def allow(self, action, priority="normal"):
        if not self._interruption_control.allow(action, priority):
            return False
        now = float(self._clock())
        with self._lock:
            points = self._refill(now)
            needed = self.cost(action, priority)
            allowed = needed == 0.0 or points >= needed
            if allowed and needed:
                self._data["points"] = points - needed
            self._save()
            return allowed

    def snapshot(self):
        now = float(self._clock())
        with self._lock:
            self._refill(now)
            self._save()
            return {"points": float(self._data["points"]), "max_points": self.max_points,
                    "refill_seconds": self.refill_seconds}

    def reset(self):
        now = float(self._clock())
        with self._lock:
            self._data = {"points": self.max_points, "updated_at": now}
            self._save()
            return self.snapshot()


_budget = None
_budget_lock = threading.Lock()


def get_proactive_attention_budget():
    global _budget
    if _budget is None:
        with _budget_lock:
            if _budget is None:
                _budget = ProactiveAttentionBudget()
    return _budget
