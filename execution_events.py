"""Typed, execution-scoped events for Akira.

The event stream is deliberately small: it is an inspectable trace for one
execution, not a global enterprise message bus. Runtime, task management, tool
execution and proactive delivery can exchange state without importing each
other or guessing from mutable Session state.
"""
from __future__ import annotations

from collections import deque
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Callable, Deque, Optional


def _now():
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ExecutionEvent:
    type: str
    task_id: Optional[str] = None
    session_id: Optional[str] = None
    source: str = "runtime"
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=_now)

    def snapshot(self):
        return {
            "type": self.type,
            "task_id": self.task_id,
            "session_id": self.session_id,
            "source": self.source,
            "data": dict(self.data),
            "timestamp": self.timestamp,
        }


class ExecutionEventStream:
    """Thread-safe bounded trace plus synchronous subscribers."""

    def __init__(self, max_events=500):
        self._events: Deque[ExecutionEvent] = deque(maxlen=max(1, int(max_events)))
        self._subscribers: dict[int, Callable[[ExecutionEvent], None]] = {}
        self._next_subscriber = 1
        self._lock = RLock()

    def emit(self, event: ExecutionEvent):
        with self._lock:
            self._events.append(event)
            callbacks = list(self._subscribers.values())
        for callback in callbacks:
            try:
                callback(event)
            except Exception:
                # Observers must never break the agent execution they observe.
                pass
        return event

    def events(self):
        with self._lock:
            return [event.snapshot() for event in self._events]

    def subscribe(self, callback):
        with self._lock:
            token = self._next_subscriber
            self._next_subscriber += 1
            self._subscribers[token] = callback
        return token

    def unsubscribe(self, token):
        with self._lock:
            return self._subscribers.pop(token, None) is not None


_current_stream: ContextVar[Optional[ExecutionEventStream]] = ContextVar(
    "akira_execution_event_stream", default=None
)
_current_identity: ContextVar[tuple[Optional[str], Optional[str]]] = ContextVar(
    "akira_execution_event_identity", default=(None, None)
)


def activate_event_stream(stream, *, task_id=None, session_id=None):
    stream_token = _current_stream.set(stream)
    identity_token = _current_identity.set((task_id, session_id))
    return stream_token, identity_token


def deactivate_event_stream(tokens):
    stream_token, identity_token = tokens
    _current_identity.reset(identity_token)
    _current_stream.reset(stream_token)


def current_event_stream():
    return _current_stream.get()


def emit_execution_event(event_type, *, source="runtime", data=None, task_id=None, session_id=None):
    stream = current_event_stream()
    if stream is None:
        return None
    current_task, current_session = _current_identity.get()
    event = ExecutionEvent(
        type=str(event_type),
        task_id=task_id if task_id is not None else current_task,
        session_id=session_id if session_id is not None else current_session,
        source=str(source),
        data=dict(data or {}),
    )
    return stream.emit(event)
