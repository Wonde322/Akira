"""Agent reasoning-loop execution boundary.

This module is the single runtime-facing entry point for an Akira agent turn.
The legacy loop still lives in ``brain`` during the migration, but callers now
depend on this boundary rather than importing ``brain.ask`` directly. This keeps
Task/Runtime ownership independent from the conversation facade and gives the
next migration steps one place to move reasoning, tool execution and recovery
without changing TaskManager callers again.
"""
from __future__ import annotations

from agent_runtime import raise_if_execution_cancelled


def run_agent_turn(goal, session_id=None):
    """Execute one agent turn inside the current runtime execution context.

    Cancellation is checked at the execution boundary before and after the
    legacy loop. As loop stages are migrated here, the same primitive can be
    used between reasoning/action iterations without changing callers.
    """
    raise_if_execution_cancelled()

    # Transitional implementation: the existing, battle-tested reasoning loop
    # remains the source of behavior until its internal stages are moved here.
    # Keeping the import local avoids a brain <-> runtime import cycle.
    from brain import ask

    result = ask(goal, session_id=session_id)

    raise_if_execution_cancelled()
    return result
