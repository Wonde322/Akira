"""Legacy import surface for the canonical Akira loop.

Brain is no longer an execution layer. All reasoning and tool execution live in
agent_loop; this module only preserves old imports during the transition.
"""
from __future__ import annotations

from agent_loop import SYSTEM_PROMPT, TOOLS, ask, get_session


class Brain:
    """Compatibility name that delegates directly to agent_loop."""

    def ask(self, message, session_id=None):
        return ask(message, session_id=session_id)

    run = ask
    handle = ask
    process = ask

    def decide(self, goal, context=None):
        raise RuntimeError("Structured decisions are owned by agent_loop.ask")


SYSTEM = SYSTEM_PROMPT
client = None
conversation = get_session(None).history
