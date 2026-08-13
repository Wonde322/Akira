import subprocess
import json
import os
import time
from datetime import datetime

MEMORY_FILE = "memory.json"
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


def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return {
            "goals": [],
            "tasks": [],
            "events": [],
            "activity": []
        }

    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as file:
            memory = json.load(file)

        if "activity" not in memory:
            memory["activity"] = []

        return memory

    except Exception:
        return {
            "goals": [],
            "tasks": [],
            "events": [],
            "activity": []
        }


def save_memory(memory):
    with open(MEMORY_FILE, "w", encoding="utf-8") as file:
        json.dump(
            memory,
            file,
            ensure_ascii=False,
            indent=2
        )


def save_session(app_name, started_at, ended_at):
    started = datetime.fromisoformat(started_at)
    ended = datetime.fromisoformat(ended_at)

    duration = (ended - started).total_seconds()

    # Не записываем совсем короткие переключения
    if duration < 5:
        return

    memory = load_memory()

    memory["activity"].append({
        "app": app_name,
        "started": started_at,
        "ended": ended_at,
        "duration_seconds": round(duration)
    })

    save_memory(memory)

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
