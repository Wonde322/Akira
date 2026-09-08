"""Legacy import surface for the canonical Akira loop.

The active runtime never executes through this module.  It exists only so old
imports and third-party callers can transition to ``agent_loop`` without
reintroducing a second execution engine.
"""
from __future__ import annotations

import agent_loop as _agent_loop

SYSTEM_PROMPT = _agent_loop.SYSTEM_PROMPT
SYSTEM = SYSTEM_PROMPT
TOOLS = _agent_loop.TOOLS
MAX_TOOL_ITERATIONS = _agent_loop.MAX_TOOL_ITERATIONS
COMPUTER_USE_MAX_STEPS = _agent_loop.COMPUTER_USE_MAX_STEPS
conversation = _agent_loop.conversation

# Legacy monkeypatch points used by the pre-runtime test surface.  The active
# runtime does not import these names from brain; ask() synchronizes them into
# the canonical module immediately before delegation.
client = _agent_loop.client
get_permission = _agent_loop.get_permission
get_tool_implementation = _agent_loop.get_tool_implementation


def _ensure_client():
    return _agent_loop._ensure_client()


def _tool_result_text(result):
    return _agent_loop._tool_result_text(result)


def execute_tool_result(function_name, arguments):
    result, _ = _agent_loop._execute(function_name, arguments)
    return result


def _sync_legacy_overrides():
    _agent_loop.client = client
    _agent_loop.get_permission = get_permission
    _agent_loop.get_tool_implementation = get_tool_implementation


def ask(message, session_id=None):
    _sync_legacy_overrides()
    return _agent_loop.ask(message, session_id=session_id)


def get_session(session_id=None):
    return _agent_loop.get_session(session_id)


class Brain:
    """Compatibility name for the canonical loop."""

    ask = staticmethod(ask)
    run = staticmethod(ask)
    handle = staticmethod(ask)
    process = staticmethod(ask)

    def decide(self, goal, context=None):
        raise RuntimeError("Structured decisions are owned by agent_loop.ask")
