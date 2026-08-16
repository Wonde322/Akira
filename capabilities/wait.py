"""Универсальная пауза. Ограничена разумным максимумом."""

import time

from config import MAX_WAIT_SECONDS

from .protocol import fail, ok


def wait(seconds, reason=None):
    """Приостанавливает выполнение на заданное число секунд."""
    if not isinstance(seconds, (int, float)) or isinstance(seconds, bool):
        return fail("invalid_seconds", "seconds должен быть числом.")

    if not 0 < seconds <= MAX_WAIT_SECONDS:
        return fail(
            "invalid_seconds",
            "seconds должен быть в диапазоне 0 < s <= " + str(MAX_WAIT_SECONDS) + ".",
        )

    time.sleep(seconds)

    return ok({"seconds": seconds, "reason": reason})
