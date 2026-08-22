"""Общие утилиты форматирования."""

import math


def format_duration(seconds):
    if isinstance(seconds, bool):
        raise ValueError("seconds должен быть неотрицательным числом")

    try:
        seconds = float(seconds)
    except (TypeError, ValueError) as error:
        raise ValueError("seconds должен быть неотрицательным числом") from error

    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("seconds должен быть неотрицательным числом")

    total_minutes = int(seconds // 60)
    hours, minutes = divmod(total_minutes, 60)

    if hours > 0:
        return f"{hours} ч {minutes} мин"

    return f"{minutes} мин"
