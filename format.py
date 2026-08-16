"""Общие утилиты форматирования."""


def format_duration(seconds):
    minutes = int(seconds // 60)
    hours = minutes // 60
    minutes = minutes % 60

    if hours > 0:
        return f"{hours} ч {minutes} мин"

    return f"{minutes} мин"