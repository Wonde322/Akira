import subprocess
import time
from datetime import datetime

from memory import add_activity_session


CHECK_INTERVAL = 10


def get_active_app():
    script = '''
    tell application "System Events"
        set frontApp to first application process whose frontmost is true
        return name of frontApp
    end tell
    '''

    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=5,
    )

    if result.returncode != 0:
        return None

    return result.stdout.strip() or None


def save_session(app_name, started_at, ended_at):
    started = datetime.fromisoformat(started_at)
    ended = datetime.fromisoformat(ended_at)
    duration = (ended - started).total_seconds()

    # Do not persist negative durations or very short app switches.
    if duration < 5:
        return

    add_activity_session(
        app_name,
        started_at,
        ended_at,
        round(duration),
    )

    minutes = int(duration // 60)
    if minutes >= 1:
        print(f"{app_name}: {minutes} мин")


class ActivityTracker:
    """Incremental activity sampler for the desktop heartbeat and CLI."""

    def __init__(self):
        self.current_app = None
        self.started_at = None

    def sample(self, app_name=None, now=None):
        app = get_active_app() if app_name is None else app_name
        now = now or datetime.now().astimezone().isoformat(timespec="seconds")
        if app != self.current_app:
            self.flush(now)
            self.current_app = app
            self.started_at = now if app else None
        elif self.started_at and (datetime.fromisoformat(now) - datetime.fromisoformat(self.started_at)).total_seconds() >= 60:
            self.flush(now)
        return {"success": True, "app": app}

    def flush(self, now=None):
        now = now or datetime.now().astimezone().isoformat(timespec="seconds")
        if self.current_app and self.started_at:
            save_session(self.current_app, self.started_at, now)
            self.started_at = now

    def pause(self):
        self.flush()
        self.current_app = None
        self.started_at = None


def run_tracker(check_interval=CHECK_INTERVAL):
    """Track foreground application sessions until interrupted.

    Keeping the loop behind an explicit entry point makes the module safe to
    import from the runtime and from tests.
    """
    print("Activity Tracker запущен.")

    tracker = ActivityTracker()

    try:
        while True:
            tracker.sample()
            time.sleep(check_interval)
    except KeyboardInterrupt:
        tracker.flush()
        print("\nActivity Tracker остановлен.")


if __name__ == "__main__":
    run_tracker()
