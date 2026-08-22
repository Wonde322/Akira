from format import format_duration
from memory import get_activity_for_period


def _normalize_days(days):
    if isinstance(days, bool):
        raise ValueError("days должен быть положительным целым числом")

    try:
        value = int(days)
    except (TypeError, ValueError) as error:
        raise ValueError("days должен быть положительным целым числом") from error

    if value < 1:
        raise ValueError("days должен быть положительным целым числом")

    return value


def get_activity_stats(days=1):
    days = _normalize_days(days)
    activity = get_activity_for_period(days)

    totals = {}

    for session in activity:
        try:
            app = session["app"]
            duration = float(session["duration_seconds"])
            if duration < 0:
                continue
            totals[app] = totals.get(app, 0) + duration
        except (KeyError, TypeError, ValueError):
            continue

    if not totals:
        return "За этот период активности пока нет."

    sorted_apps = sorted(
        totals.items(),
        key=lambda item: item[1],
        reverse=True,
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
