"""Lifecycle wiring for local desktop services; no second agent executor."""
from __future__ import annotations

from threading import Event

from activity_tracker import ActivityTracker
from agent_runtime import get_agent_runtime
from akira_daemon import AkiraDaemon
from proactive_runtime import ProactiveHeartbeat


class DesktopServices:
    def __init__(self, interval=10, scheduler=None, awareness=None, tasks=None, tracker=None):
        self._scheduler = scheduler
        self._awareness = awareness
        self._tasks = tasks
        self._tracker = tracker or ActivityTracker()
        self._stopping = Event()
        self.heartbeat = ProactiveHeartbeat()
        self.heartbeat.register_source("scheduler", self._schedule)
        self.heartbeat.register_source("awareness", self._sample)
        self.heartbeat.register_source("activity", self._track)
        self._daemon = AkiraDaemon(
            runtime=get_agent_runtime(), heartbeat_interval=interval,
            heartbeat=self.heartbeat.tick,
        )

    def start(self):
        if self._daemon.is_alive:
            return
        self._stopping.clear()
        if self._tasks is None:
            from task_runtime import get_runtime
            self._tasks = get_runtime()
        self._daemon.start(background=True)

    def _schedule(self):
        if self._stopping.is_set():
            return
        if self._scheduler is None:
            from scheduler import get_scheduler
            self._scheduler = get_scheduler()
        return self._scheduler.tick()

    def _sample(self):
        if self._stopping.is_set():
            return
        if self._awareness is None:
            from awareness import get_awareness
            self._awareness = get_awareness()
        return self._awareness.sample(capture=False)

    def _track(self):
        if self._stopping.is_set():
            return
        if self._awareness is not None and not getattr(self._awareness, "enabled", True):
            self._tracker.pause()
            return
        if self._awareness is not None and hasattr(self._awareness, "state"):
            from context_triggers import ui_context
            state = self._awareness.state().get("last_state") or {}
            context = ui_context(state.get("ui"))
            if context["app"]:
                return self._tracker.sample(app_name=context["app"], context=context["title"])
        return self._tracker.sample()

    def request_stop(self):
        if self._stopping.is_set():
            return
        self._stopping.set()
        self._daemon.request_stop()
        if self._tasks is not None:
            self._tasks.shutdown(wait=False)

    def is_running(self):
        active = self._tasks is not None and self._tasks.has_active()
        if not self._daemon.is_alive and not active:
            self._tracker.flush()
            return False
        return True
