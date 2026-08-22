\
"""
Persistent lifecycle host for Akira.

The daemon owns the runtime lifetime.
It does not create a second agent runtime.
"""

from dataclasses import dataclass, field
from threading import Event, Thread
from typing import Any
import time


LIFECYCLE_STATES = {
    "created",
    "starting",
    "running",
    "stopping",
    "stopped",
    "failed",
}


@dataclass
class DaemonState:
    status: str = "created"
    started_at: float | None = None
    stopped_at: float | None = None
    last_error: str | None = None
    cycles: int = 0
    metadata: dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "status": self.status,
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
            "last_error": self.last_error,
            "cycles": self.cycles,
            "metadata": self.metadata,
        }


class AkiraDaemon:
    """
    Persistent host for one AkiraRuntime instance.

    Background work is opt-in: the daemon itself does not force
    proactive actions or notifications.
    """

    def __init__(
        self,
        runtime=None,
        heartbeat_interval=5.0,
    ):
        if runtime is None:
            from akira_runtime import AkiraRuntime
            runtime = AkiraRuntime()

        self.runtime = runtime
        self.heartbeat_interval = heartbeat_interval
        self.state = DaemonState()

        self._stop_event = Event()
        self._thread = None

    @property
    def running(self):
        return self.state.status == "running"

    def status(self):
        data = self.state.to_dict()
        data["runtime"] = (
            self.runtime.status()
            if hasattr(self.runtime, "status")
            else None
        )
        return data

    def start(self, background=False):
        if self.running:
            return self.status()

        if self.state.status == "stopping":
            raise RuntimeError(
                "Cannot start daemon while it is stopping"
            )

        self.state.status = "starting"
        self.state.started_at = time.time()
        self.state.stopped_at = None
        self.state.last_error = None
        self._stop_event.clear()

        try:
            self.state.status = "running"

            if background:
                self._thread = Thread(
                    target=self._heartbeat_loop,
                    name="AkiraDaemon",
                    daemon=True,
                )
                self._thread.start()

            return self.status()

        except Exception as exc:
            self.state.status = "failed"
            self.state.last_error = str(exc)
            raise

    def _heartbeat_loop(self):
        while not self._stop_event.is_set():
            self.tick()

            self._stop_event.wait(
                self.heartbeat_interval
            )

    def tick(self):
        if not self.running:
            return []

        self.state.cycles += 1

        try:
            heartbeat = getattr(
                self.runtime,
                "heartbeat_tick",
                None,
            )

            if callable(heartbeat):
                result = heartbeat()
                return (
                    result
                    if result is not None
                    else []
                )

            return []

        except Exception as exc:
            self.state.last_error = str(exc)

            return [{
                "success": False,
                "error": str(exc),
                "source": "heartbeat",
            }]

    def handle(
        self,
        text=None,
        voice_text=None,
        observation=None,
        metadata=None,
    ):
        if not self.running:
            self.start(background=False)

        return self.runtime.handle(
            text=text,
            voice_text=voice_text,
            observation=observation,
            metadata=metadata,
        )

    def run_agent_loop(
        self,
        goal,
        observer=None,
        executor=None,
        max_iterations=20,
    ):
        if not self.running:
            self.start(background=False)

        return self.runtime.run_agent_loop(
            goal=goal,
            observer=observer,
            executor=executor,
            max_iterations=max_iterations,
        )

    def stop(self, timeout=5.0):
        if self.state.status in {
            "created",
            "stopped",
        }:
            self.state.status = "stopped"
            self.state.stopped_at = time.time()
            return self.status()

        self.state.status = "stopping"
        self._stop_event.set()

        thread = self._thread

        if (
            thread is not None
            and thread.is_alive()
        ):
            thread.join(timeout=timeout)

        self._thread = None
        self.state.status = "stopped"
        self.state.stopped_at = time.time()

        return self.status()


def create_daemon(
    runtime=None,
    heartbeat_interval=5.0,
):
    return AkiraDaemon(
        runtime=runtime,
        heartbeat_interval=heartbeat_interval,
    )
