"""Persistent control over when Akira may interrupt the user.

This is intentionally separate from feedback and the attention budget. Feedback
answers whether a kind of intervention is welcome; the budget answers how much
attention has recently been consumed; this layer represents an explicit current
mode chosen by the user or application.
"""
from __future__ import annotations

import json
import os
import threading
import time


class ProactiveInterruptionControl:
    MODES = {"normal", "focus", "quiet"}

    def __init__(self, path="runtime/proactive_interruption_control.json", clock=None):
        self.path = path
        self._clock = clock or time.time
        self._lock = threading.RLock()
        self._data = self._load()
        self._normalize()

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

    def _normalize(self):
        mode = str(self._data.get("mode") or "normal").lower()
        self._data["mode"] = mode if mode in self.MODES else "normal"
        quiet_until = self._data.get("quiet_until")
        try:
            self._data["quiet_until"] = float(quiet_until) if quiet_until is not None else None
        except (TypeError, ValueError):
            self._data["quiet_until"] = None

    def _expire(self, now):
        if self._data.get("mode") == "quiet":
            until = self._data.get("quiet_until")
            if until is not None and now >= until:
                self._data["mode"] = "normal"
                self._data["quiet_until"] = None
                self._save()

    def set_mode(self, mode, duration_seconds=None):
        mode = str(mode or "").lower()
        if mode not in self.MODES:
            raise ValueError("mode must be normal, focus, or quiet")
        now = float(self._clock())
        with self._lock:
            self._data["mode"] = mode
            self._data["quiet_until"] = None
            if mode == "quiet" and duration_seconds is not None:
                duration = float(duration_seconds)
                if duration <= 0:
                    raise ValueError("duration_seconds must be positive")
                self._data["quiet_until"] = now + duration
            self._save()
            return self.snapshot()

    def allow(self, action, priority="normal"):
        now = float(self._clock())
        action = str(getattr(action, "value", action) or "")
        priority = str(priority or "normal")
        with self._lock:
            self._expire(now)
            mode = self._data["mode"]
            if priority == "high":
                return True
            if mode == "normal":
                return True
            if mode == "focus":
                return action == "notify" and priority == "low"
            return False

    def snapshot(self):
        now = float(self._clock())
        with self._lock:
            self._expire(now)
            return {"mode": self._data["mode"], "quiet_until": self._data.get("quiet_until")}

    def reset(self):
        with self._lock:
            self._data = {"mode": "normal", "quiet_until": None}
            self._save()
            return self.snapshot()


_control = None
_control_lock = threading.Lock()


def get_proactive_interruption_control():
    global _control
    if _control is None:
        with _control_lock:
            if _control is None:
                _control = ProactiveInterruptionControl()
    return _control
