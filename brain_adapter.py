"""Stable object adapter for the canonical brain module.

The brain implementation is intentionally a module-level compatibility facade;
this adapter lets the unified runtime consume it as a normal provider without
inventing a second Brain class or execution loop.
"""
from __future__ import annotations


class BrainAdapter:
    def ask(self, text, **kwargs):
        from brain import ask
        return ask(text)
