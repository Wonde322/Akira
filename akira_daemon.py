"""Always-on runtime for Akira."""
from __future__ import annotations

import signal
import threading
from datetime import datetime

HEARTBEAT_INTERVAL = 15.0


class AkiraDaemon:
    """Long-lived Akira infrastructure process."""

    def __init__(self, heartbeat_interval=HEARTBEAT_INTERVAL):
        self.heartbeat_interval = float(heartbeat_interval)
        self._stop_event = threading.Event()
        self._started = False
        self._heartbeat_count = 0
        self._last_heartbeat = None
        self._runtime = None
        self._scheduler = None
        self._event_bus = None
        self._awareness = None
        self._task_watchdog = None

    def start(self):
        if self._started:
            return {"success": True, "started": False, "output": "Akira daemon уже запущен."}
        self._install_signal_handlers()
        from task_runtime import get_runtime
        from scheduler import get_scheduler
        from event_bus import get_event_bus
        from awareness import get_awareness
        from task_watchdog import get_task_watchdog
        self._runtime = get_runtime()
        self._scheduler = get_scheduler()
        self._event_bus = get_event_bus()
        self._awareness = get_awareness()
        self._task_watchdog = get_task_watchdog()
        self._started = True
        self._heartbeat()
        return {"success": True, "started": True, "heartbeat_interval": self.heartbeat_interval,
                "output": "Akira daemon запущен."}

    def stop(self):
        if not self._started:
            return {"success": True, "stopped": False, "output": "Akira daemon не был запущен."}
        self._stop_event.set()
        self._started = False
        return {"success": True, "stopped": True, "output": "Akira daemon остановлен."}

    def run(self):
        result = self.start()
        if not result.get("success"):
            return result
        print("Akira daemon: RUNNING")
        try:
            while not self._stop_event.wait(self.heartbeat_interval):
                self._heartbeat()
        finally:
            self.stop()
        print("Akira daemon: STOPPED")
        return {"success": True, "output": "Akira daemon завершил работу."}

    def _heartbeat(self):
        self._heartbeat_count += 1
        self._last_heartbeat = datetime.now().isoformat(timespec="seconds")
        self._maintain_runtime()
        self._tick_scheduler()
        self._maintain_event_bus()
        self._sample_awareness()

    def _maintain_runtime(self):
        runtime = self._runtime
        if runtime is None:
            return
        try:
            runtime.list_tasks(limit=1)
        except Exception as error:
            print("[Akira daemon] runtime health error:", error)
        watchdog = self._task_watchdog
        if watchdog is not None:
            try:
                result = watchdog.scan()
                if result.get("stalled") or result.get("interrupted"):
                    print("[Akira daemon] task watchdog:", result)
            except Exception as error:
                print("[Akira daemon] task watchdog error:", error)

    def _tick_scheduler(self):
        if self._scheduler is None:
            return
        try:
            result = self._scheduler.tick()
            launched = result.get("launched", [])
            if launched:
                print("[Akira daemon] scheduled tasks launched:", launched)
        except Exception as error:
            print("[Akira daemon] scheduler error:", error)

    def _maintain_event_bus(self):
        if self._event_bus is None:
            return
        try:
            self._event_bus.list_triggers(limit=1)
        except Exception as error:
            print("[Akira daemon] event bus error:", error)

    def _sample_awareness(self):
        if self._awareness is None:
            return
        try:
            result = self._awareness.sample()
            if result.get("changed"):
                print("[Akira daemon] desktop state changed.")
        except Exception as error:
            print("[Akira daemon] awareness error:", error)

    def health(self):
        runtime = self._runtime
        runtime_ok = False
        task_count = 0
        active_count = 0
        if runtime is not None:
            try:
                with runtime._lock:
                    task_count = len(runtime._tasks)
                    active_count = runtime._active_count()
                runtime_ok = True
            except Exception:
                runtime_ok = False
        return {"success": True, "running": self._started, "heartbeat_count": self._heartbeat_count,
                "last_heartbeat": self._last_heartbeat, "heartbeat_interval": self.heartbeat_interval,
                "runtime": {"ok": runtime_ok, "task_count": task_count, "active_tasks": active_count},
                "timestamp": datetime.now().isoformat(timespec="seconds")}

    def _install_signal_handlers(self):
        def handle_signal(signum, frame):
            print(f"\n[Akira daemon] signal {signum}; stopping...")
            self.stop()
        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)


_daemon = None
_daemon_lock = threading.Lock()


def get_daemon():
    global _daemon
    if _daemon is None:
        with _daemon_lock:
            if _daemon is None:
                _daemon = AkiraDaemon()
    return _daemon


def daemon_health():
    return get_daemon().health()


if __name__ == "__main__":
    get_daemon().run()
