"""Single execution boundary for Akira agent turns.

UI, voice, foreground tasks and background tasks should enter the agent through
this module instead of calling the reasoning implementation directly.  The
actual loop still lives in ``brain`` for now; keeping that implementation behind
this boundary lets us move it out without changing every caller again.
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass(frozen=True)
class ExecutionContext:
    goal: str
    session_id: Optional[str]
    mode: str
    task_id: Optional[str] = None


_current_execution: ContextVar[Optional[ExecutionContext]] = ContextVar(
    "akira_execution_context", default=None
)


class AgentRuntime:
    """Owns entry into one agent execution.

    ``executor`` is intentionally injected/lazy-resolved.  Task infrastructure
    therefore depends on the runtime contract, not on ``brain.ask``.
    """

    def __init__(self, executor: Optional[Callable[..., str]] = None):
        self._executor = executor

    def set_executor(self, executor: Callable[..., str]):
        self._executor = executor

    def _resolve_executor(self):
        if self._executor is None:
            # Temporary compatibility adapter while the existing loop is moved
            # out of brain.py.  No task manager imports brain directly.
            from brain import ask
            self._executor = ask
        return self._executor

    def run(self, goal, session_id=None, *, mode="foreground", task_id=None):
        goal = str(goal or "").strip()
        if not goal:
            raise ValueError("AgentRuntime requires a non-empty goal")

        context = ExecutionContext(
            goal=goal,
            session_id=session_id,
            mode=str(mode or "foreground"),
            task_id=task_id,
        )
        token = _current_execution.set(context)
        try:
            return self._resolve_executor()(goal, session_id=session_id)
        finally:
            _current_execution.reset(token)


def current_execution():
    return _current_execution.get()


_default_runtime = AgentRuntime()


def get_agent_runtime():
    return _default_runtime
