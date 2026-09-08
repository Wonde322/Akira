"""Legacy import surface for the canonical Akira loop.

The active runtime never executes through this module. All reasoning, model
turns and tool execution remain owned by ``agent_loop``.
"""
from __future__ import annotations

from agent_loop import SYSTEM_PROMPT, TOOLS, ask, get_session

SYSTEM = SYSTEM_PROMPT


class Brain:
    """Compatibility name that delegates to the canonical loop."""

    def ask(self, message, session_id=None):
        return ask(message, session_id=session_id)

    run = ask
    handle = ask
    process = ask

    def decide(self, goal, context=None):
        raise RuntimeError("Structured decisions are owned by agent_loop.ask")


def get_brain():
    """Return a compatibility Brain instance without creating another loop."""
    return Brain()
