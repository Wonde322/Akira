"""Single execution boundary and lifecycle control for Akira agent runs.

UI, voice, foreground tasks and background tasks enter the agent through this
module. The reasoning implementation is still adapted from ``brain`` for now,
but task ownership, execution identity and cooperative cancellation live here.
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from threading import Event, RLock
from typing import Callable, Optional


class ExecutionCancelled(RuntimeError):
    """Raised when an agent loop observes cooperative cancellation."""


@dataclass
class ExecutionContext:
    goal: str
    session_id: Optional[str]
    mode: str
    task_id: Optional[str] = None
    _cancel_event: Event | None = None

    @property
    def cancelled(self) -> bool:
        return bool(self._cancel_event and self._cancel_event.is_set())

    def raise_if_cancelled(self):
        if self.cancelled:
            raise ExecutionCancelled("Agent execution was cancelled")


_current_execution: ContextVar[Optional[ExecutionContext]] = ContextVar(
    "akira_execution_context", default=None
)


class AgentRuntime:
    """Owns one agent execution and its cooperative lifecycle controls.

    Callers depend on this runtime contract rather than importing ``brain.ask``.
    Active task ids are tracked here, making cancellation an execution concern
    instead of a ThreadPool concern.
    """

    def __init__(self, executor: Optional[Callable[..., str]] = None):
        self._executor = executor
        self._lock = RLock()
        self._active = {}

    def set_executor(self, executor: Callable[..., str]):
        self._executor = executor

    def _resolve_executor(self):
        if self._executor is None:
            # Compatibility adapter while the existing loop is migrated out of
            # brain.py. No caller outside this runtime imports brain directly.
            from brain import ask
            self._executor = ask
        return self._executor

    def run(self, goal, session_id=None, *, mode="foreground", task_id=None):
        goal = str(goal or "").strip()
        if not goal:
            raise ValueError("AgentRuntime requires a non-empty goal")

        task_key = str(task_id or "") or None
        cancel_event = Event()
        context = ExecutionContext(
            goal=goal,
            session_id=session_id,
            mode=str(mode or "foreground"),
            task_id=task_key,
            _cancel_event=cancel_event,
        )

        if task_key:
            with self._lock:
                self._active[task_key] = cancel_event

        token = _current_execution.set(context)
        try:
            context.raise_if_cancelled()
            result = self._resolve_executor()(goal, session_id=session_id)
            context.raise_if_cancelled()
            return result
        finally:
            _current_execution.reset(token)
            if task_key:
                with self._lock:
                    self._active.pop(task_key, None)

    def cancel(self, task_id):
        task_key = str(task_id or "")
        if not task_key:
            return False
        with self._lock:
            event = self._active.get(task_key)
        if event is None:
            return False
        event.set()
        return True

    def is_active(self, task_id):
        with self._lock:
            return str(task_id or "") in self._active


def current_execution():
    return _current_execution.get()


def execution_cancelled():
    context = current_execution()
    return bool(context and context.cancelled)


def raise_if_execution_cancelled():
    context = current_execution()
    if context is not None:
        context.raise_if_cancelled()


_default_runtime = AgentRuntime()


def get_agent_runtime():
    return _default_runtime
