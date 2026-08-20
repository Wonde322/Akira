"""Detect meaningful patterns in desktop context over time."""
from __future__ import annotations

import threading
import time
from collections import deque

from context_triggers import ui_context


class ContextPatternEngine:
    """Turns repeated context samples into sparse, high-signal insights."""

    def __init__(self, dwell_seconds=15 * 60, revisit_count=3,
                 revisit_window_seconds=10 * 60, cooldown_seconds=30 * 60,
                 clock=None):
        self.dwell_seconds = float(dwell_seconds)
        self.revisit_count = max(2, int(revisit_count))
        self.revisit_window_seconds = float(revisit_window_seconds)
        self.cooldown_seconds = float(cooldown_seconds)
        self._clock = clock or time.monotonic
        self._lock = threading.RLock()
        self._current = None
        self._current_since = None
        self._history = deque()
        self._last_emitted = {}
        self._dwell_emitted_for_visit = False

    @staticmethod
    def _key(ui):
        context = ui_context(ui)
        return context["app"].strip(), context["title"].strip()

    @staticmethod
    def _label(key):
        app, title = key
        if app and title:
            return f"{app} — {title}"
        return app or title or "текущем контексте"

    def _allow(self, pattern_key, now):
        previous = self._last_emitted.get(pattern_key)
        if previous is not None and now - previous < self.cooldown_seconds:
            return False
        self._last_emitted[pattern_key] = now
        return True

    def _prune(self, now):
        cutoff = now - self.revisit_window_seconds
        while self._history and self._history[0][0] < cutoff:
            self._history.popleft()

    def observe(self, ui, now=None):
        now = self._clock() if now is None else float(now)
        key = self._key(ui)
        insights = []
        with self._lock:
            if self._current is None:
                self._current = key
                self._current_since = now
                self._history.append((now, key))
                return insights

            if key == self._current:
                elapsed = max(0.0, now - self._current_since)
                if elapsed >= self.dwell_seconds and not self._dwell_emitted_for_visit:
                    pattern_key = ("dwell", key, self._current_since)
                    if self._allow(pattern_key, now):
                        minutes = max(1, int(elapsed // 60))
                        insights.append({
                            "type": "desktop.context.dwell",
                            "context": {"app": key[0], "title": key[1]},
                            "seconds": elapsed,
                            "message": f"Ты уже около {minutes} мин находишься в {self._label(key)}.",
                        })
                    self._dwell_emitted_for_visit = True
                return insights

            self._current = key
            self._current_since = now
            self._dwell_emitted_for_visit = False
            self._history.append((now, key))
            self._prune(now)
            visits = sum(1 for _, seen_key in self._history if seen_key == key)
            if visits >= self.revisit_count:
                pattern_key = ("repeated", key)
                if self._allow(pattern_key, now):
                    insights.append({
                        "type": "desktop.context.repeated",
                        "context": {"app": key[0], "title": key[1]},
                        "count": visits,
                        "window_seconds": self.revisit_window_seconds,
                        "message": f"Ты уже {visits} раз за последнее время возвращался к {self._label(key)}.",
                    })
        return insights


_engine = None
_engine_lock = threading.Lock()


def get_context_pattern_engine():
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = ContextPatternEngine()
    return _engine
