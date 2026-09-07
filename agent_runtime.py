"""Canonical execution boundary for Akira.

Every input channel becomes a RequestContext at the gateway and enters this
runtime. The runtime owns lifecycle and cancellation; agent_loop owns reasoning
and tool execution.
"""
from __future__ import annotations

from threading import Event, RLock
from typing import Callable, Optional

from execution_context import (
    ExecutionContext,
    activate_execution,
    deactivate_execution,
    raise_if_execution_cancelled,
)
from execution_policy import choose_execution_policy


def _run_agent_turn(goal, session_id=None):
    """Run one turn through the single canonical reasoning loop."""
    import agent_loop
    return agent_loop.ask(goal, session_id=session_id)


class AgentRuntime:
    """Own execution lifecycle and delegate reasoning to one canonical loop."""

    def __init__(self, executor: Optional[Callable[..., str]] = None):
        self._executor = executor or _run_agent_turn
        self._lock = RLock()
        self._active: dict[str, Event] = {}
        self._pending_cancel: set[str] = set()

    @staticmethod
    def _normalize_request(request, session_id=None):
        if hasattr(request, "primary_text"):
            text = request.primary_text()
            metadata = getattr(request, "metadata", {}) or {}
            session_id = metadata.get("session_id") or session_id
            source = getattr(request, "source", "text")
        else:
            text = request
            source = "text"
        return str(text or "").strip(), session_id, source

    def set_executor(self, executor: Callable[..., str]):
        if not callable(executor):
            raise TypeError("executor must be callable")
        with self._lock:
            self._executor = executor

    def run(self, request, session_id=None, *, mode="auto", task_id=None):
        goal, session_id, source = self._normalize_request(request, session_id)
        if not goal:
            raise ValueError("AgentRuntime requires a non-empty goal")

        task_key = str(task_id or "") or None
        policy = choose_execution_policy(
            goal,
            mode=mode,
            background=bool(task_key and str(mode or "").lower() == "background"),
        )
        cancel_event = Event()

        if task_key:
            with self._lock:
                if task_key in self._active:
                    raise RuntimeError("An execution with this task_id is already active")
                if task_key in self._pending_cancel:
                    self._pending_cancel.discard(task_key)
                    cancel_event.set()
                self._active[task_key] = cancel_event

        context = ExecutionContext(
            goal=goal,
            session_id=session_id,
            mode=policy.value,
            task_id=task_key,
            _cancel_event=cancel_event,
        )
        token = activate_execution(context)
        try:
            raise_if_execution_cancelled()
            result = self._executor(goal, session_id=session_id)
            raise_if_execution_cancelled()
            return result
        finally:
            deactivate_execution(token)
            if task_key:
                with self._lock:
                    self._active.pop(task_key, None)
                    self._pending_cancel.discard(task_key)

    def cancel(self, task_id):
        task_key = str(task_id or "")
        if not task_key:
            return False
        with self._lock:
            event = self._active.get(task_key)
            if event is None:
                self._pending_cancel.add(task_key)
                return False
            event.set()
            return True

    def is_active(self, task_id):
        with self._lock:
            return str(task_id or "") in self._active


_default_runtime = AgentRuntime()


def get_agent_runtime():
    return _default_runtime
