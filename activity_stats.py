import json
import os
from datetime import datetime, timedelta


MEMORY_FILE = "memory.json"


def load_activity():
    if not os.path.exists(MEMORY_FILE):
        return []

    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as file:
            memory = json.load(file)

        return memory.get("activity", [])

    except Exception:
        return []


def format_duration(seconds):
    minutes = int(seconds // 60)

    hours = minutes // 60
    minutes = minutes % 60

    if hours > 0:
        return f"{hours} ч {minutes} мин"

    return f"{minutes} мин"


def get_activity_stats(days=1):
    activity = load_activity()

    cutoff = datetime.now() - timedelta(days=days)

    totals = {}

    for session in activity:
        try:
            started = datetime.fromisoformat(session["started"])

            if started < cutoff:
                continue

            app = session["app"]
            duration = session["duration_seconds"]

            totals[app] = totals.get(app, 0) + duration

        except (KeyError, ValueError):
            continue

    if not totals:
        return "За этот период активности пока нет."

    sorted_apps = sorted(
        totals.items(),
        key=lambda item: item[1],
        reverse=True
    )

    title = "Сегодня" if days == 1 else f"Последние {days} дней"

    result = title + "\n\n"

    for app, seconds in sorted_apps:
        result += f"{app:<25} {format_duration(seconds)}\n"

    return result.strip()


if __name__ == "__main__":
    print(get_activity_stats(1))
    print()
    print(get_activity_stats(7))
