"""Универсальный инструмент завершения задачи computer-use.

finish_task — без side effects, policy auto: явный сигнал модели о том,
что цель достигнута или дальше действовать нельзя. Brain перехватывает
его в цикле и завершает задачу.
"""

from .protocol import fail, ok


def finish_task(result):
    """Завершает компьютерную задачу с итогом."""
    if not isinstance(result, str) or not result.strip():
        return fail("invalid_result", "result должен быть непустой строкой.")

    return ok({"finished": True, "result": result})