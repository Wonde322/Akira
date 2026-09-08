"""Legacy import surface for the canonical Akira loop.

The active runtime never executes through this module. All reasoning, model
turns and tool execution remain owned by ``agent_loop``.
"""
from __future__ import annotations

import agent_loop as _agent_loop

SYSTEM_PROMPT = _agent_loop.SYSTEM_PROMPT
SYSTEM = SYSTEM_PROMPT
TOOLS = _agent_loop.TOOLS
get_permission = _agent_loop.get_permission
get_tool_implementation = _agent_loop.get_tool_implementation


def _tool_result_text(result):
    return _agent_loop._tool_result_text(result)


def execute_tool_result(function_name, arguments):
    return _agent_loop.execute_tool_result(function_name, arguments)


def ask(message, session_id=None):
    return _agent_loop.ask(message, session_id=session_id)


def get_session(session_id=None):
    return _agent_loop.get_session(session_id)


class Brain:
    """Compatibility name that delegates to the canonical loop."""

    ask = staticmethod(ask)
    run = staticmethod(ask)
    handle = staticmethod(ask)
    process = staticmethod(ask)

    def decide(self, goal, context=None):
        raise RuntimeError("Structured decisions are owned by agent_loop.ask")
