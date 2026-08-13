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
        text=True
    )

    if result.returncode != 0:
        return None

    return result.stdout.strip()


def save_session(app_name, started_at, ended_at):
    started = datetime.fromisoformat(started_at)
    ended = datetime.fromisoformat(ended_at)

    duration = (ended - started).total_seconds()

    # Не записываем совсем короткие переключения
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
        print(
            f"{app_name}: {minutes} мин"
        )


print("Activity Tracker запущен.")

current_app = None
started_at = None

try:
    while True:
        app = get_active_app()
        now = datetime.now().isoformat(timespec="seconds")

        if app != current_app:

            if current_app is not None and started_at is not None:
                save_session(
                    current_app,
                    started_at,
                    now
                )

            current_app = app
            started_at = now

        time.sleep(CHECK_INTERVAL)

except KeyboardInterrupt:

    if current_app is not None and started_at is not None:
        now = datetime.now().isoformat(timespec="seconds")

        save_session(
            current_app,
            started_at,
            now
        )

    print("\nActivity Tracker остановлен.")
