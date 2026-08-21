"""Execution-local state shared by agent runtimes and loops.

This module owns the identity and cooperative cancellation state of one agent
execution. It intentionally knows nothing about task scheduling, LLM providers,
tools or UI, so execution code can depend on it without importing AgentRuntime.
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from threading import Event
from typing import Optional


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


def activate_execution(context: ExecutionContext):
    """Make an execution context current and return its reset token."""
    return _current_execution.set(context)


def deactivate_execution(token):
    """Restore the execution context that preceded ``activate_execution``."""
    _current_execution.reset(token)


def current_execution():
    return _current_execution.get()


def execution_cancelled():
    context = current_execution()
    return bool(context and context.cancelled)


def raise_if_execution_cancelled():
    context = current_execution()
    if context is not None:
        context.raise_if_cancelled()
