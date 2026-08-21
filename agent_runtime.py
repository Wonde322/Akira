"""Single execution boundary and lifecycle control for Akira agent runs.

UI, voice, foreground tasks and background tasks enter the agent through this
module. Task ownership and lifecycle live here; execution-local identity and
cooperative cancellation are provided by ``execution_context`` so the reasoning
loop can eventually depend on the same primitive without importing this runtime.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import Event, RLock
from typing import Callable, Optional

from execution_context import (
    ExecutionCancelled,
    ExecutionContext,
    activate_execution,
    current_execution,
    deactivate_execution,
    execution_cancelled,
    raise_if_execution_cancelled,
)


_guard_lock = RLock()


def _install_cancellation_guards(agent_loop):
    """Install cooperative cancellation at the current loop boundaries.

    This compatibility bridge remains temporary while ``agent_loop`` is being
    migrated to call the execution-context primitive directly. Context state is
    no longer owned by AgentRuntime, so the loop can adopt the same primitive
    without a runtime import or a circular dependency.
    """
    with _guard_lock:
        if not getattr(agent_loop, "_akira_cancellation_guards", False):
            original_tools_for_reasoning = agent_loop._tools_for_reasoning
            original_execute_and_audit = agent_loop._execute_and_audit

            def guarded_tools_for_reasoning(*args, **kwargs):
                raise_if_execution_cancelled()
                return original_tools_for_reasoning(*args, **kwargs)

            def guarded_execute_and_audit(*args, **kwargs):
                raise_if_execution_cancelled()
                return original_execute_and_audit(*args, **kwargs)

            agent_loop._tools_for_reasoning = guarded_tools_for_reasoning
            agent_loop._execute_and_audit = guarded_execute_and_audit
            agent_loop._akira_cancellation_guards = True


def _run_agent_turn(goal, session_id=None):
    """Execute the real reasoning loop owned by ``agent_loop``."""
    raise_if_execution_cancelled()
    import agent_loop
    _install_cancellation_guards(agent_loop)
    result = agent_loop.ask(goal, session_id=session_id)
    raise_if_execution_cancelled()
    return result


class AgentRuntime:
    """Owns one agent execution and its cooperative lifecycle controls."""

    def __init__(self, executor: Optional[Callable[..., str]] = None):
        self._executor = executor
        self._lock = RLock()
        self._active = {}

    def set_executor(self, executor: Callable[..., str]):
        self._executor = executor

    def _resolve_executor(self):
        if self._executor is None:
            self._executor = _run_agent_turn
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

        token = activate_execution(context)
        try:
            context.raise_if_cancelled()
            result = self._resolve_executor()(goal, session_id=session_id)
            context.raise_if_cancelled()
            return result
        finally:
            deactivate_execution(token)
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


_default_runtime = AgentRuntime()


def get_agent_runtime():
    return _default_runtime
