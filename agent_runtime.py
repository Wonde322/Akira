"""Single execution boundary and lifecycle control for Akira agent runs.

UI, voice, foreground tasks and persistent background tasks enter the agent
through this module. Task scheduling lives outside this runtime; execution-local
identity and cooperative cancellation live in ``execution_context``.
"""
from __future__ import annotations

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
    """Compatibility bridge until cancellation checks live directly in agent_loop."""
    with _guard_lock:
        if getattr(agent_loop, "_akira_cancellation_guards", False):
            return
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
    """Run through the public compatibility entry point.

    ``brain`` remains a thin facade over the real agent loop, while using its
    public entry point preserves existing callers and test-level substitution.
    """
    raise_if_execution_cancelled()
    import agent_loop
    _install_cancellation_guards(agent_loop)
    from brain import ask
    result = ask(goal, session_id=session_id)
    raise_if_execution_cancelled()
    return result


class AgentRuntime:
    """Owns active execution contexts and cooperative cancellation signals.

    ``cancel`` also records cancellation requested before a worker has reached
    runtime registration. This closes the scheduler→runtime race for background
    tasks without forcing schedulers to know about execution internals.
    """

    def __init__(self, executor: Optional[Callable[..., str]] = None):
        self._executor = executor
        self._lock = RLock()
        self._active = {}
        self._pending_cancel = set()

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
        if task_key:
            with self._lock:
                if task_key in self._pending_cancel:
                    self._pending_cancel.discard(task_key)
                    cancel_event.set()
                self._active[task_key] = cancel_event

        context = ExecutionContext(
            goal=goal,
            session_id=session_id,
            mode=str(mode or "foreground"),
            task_id=task_key,
            _cancel_event=cancel_event,
        )
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
