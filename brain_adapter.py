"""Stable object adapter for the canonical brain module."""
from __future__ import annotations


class BrainAdapter:
    """Expose the module-level brain facade as a runtime provider."""

    def ask(self, text, **kwargs):
        from brain import ask
        try:
            return ask(text, **kwargs)
        except TypeError:
            return ask(text)
