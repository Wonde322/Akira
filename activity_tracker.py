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


def run_tracker(check_interval=CHECK_INTERVAL):
    """Track foreground application sessions until interrupted.

    Keeping the loop behind an explicit entry point makes the module safe to
    import from the runtime and from tests.
    """
    print("Activity Tracker запущен.")

    current_app = None
    started_at = None

    try:
        while True:
            app = get_active_app()
            now = datetime.now().isoformat(timespec="seconds")

            if app != current_app:
                if current_app is not None and started_at is not None:
                    save_session(current_app, started_at, now)

                current_app = app
                started_at = now if app is not None else None

            time.sleep(check_interval)
    except KeyboardInterrupt:
        if current_app is not None and started_at is not None:
            now = datetime.now().isoformat(timespec="seconds")
            save_session(current_app, started_at, now)
        print("\nActivity Tracker остановлен.")


if __name__ == "__main__":
    run_tracker()
