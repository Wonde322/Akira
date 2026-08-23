"""Compatibility facade for Akira's agent runtime."""
import importlib as _importlib
import sys as _sys

import agent_loop as _agent_loop

_agent_loop = _importlib.reload(_agent_loop)

_agent_loop.STATE_CHANGING_TOOLS = (
    "click", "select", "type", "scroll", "drag", "key",
)

_POLICY = """
КРИТИЧЕСКИЕ ПРАВИЛА ВЫПОЛНЕНИЯ И ПРОВЕРКИ:
1. observe используется только когда для проверки действительно нужны пиксели
или визуальное состояние интерфейса. Не вызывай observe автоматически после
open, close, filesystem или shell, если инструмент уже вернул авторитетное
evidence (process_state, filesystem_state или command_result).
2. Иконка приложения в Dock, Launchpad или панели не является доказательством
запущенного процесса.
3. Если open вернул running=true или activated=true, цель открытия приложения
уже выполнена. Немедленно заверши этот шаг и не открывай приложение повторно.
4. Для открытия или активации приложения сначала используй open. Не используй
shell/Terminal как fallback для той же операции, если open не вернул явную
ошибку. Свёрнутое приложение должно быть активировано через open, а не
"открыто" второй независимой командой.
5. Не показывай пользователю внутренние результаты observe, JSON, evidence,
task state, "проверку контекста" или другие служебные сообщения. Пользователь
получает только короткий нормальный итог.
6. Новая команда пользователя заменяет текущую задачу. Не продолжай старую
задачу и не выполняй устаревшие действия после появления новой команды.
"""
_agent_loop.SYSTEM_PROMPT += _POLICY
_agent_loop.COMPUTER_USE_SYSTEM_PROMPT += _POLICY

_original_finish_answer = _agent_loop._finish_answer

def _finish_answer(result):
    """Never expose structured verification evidence as chat text."""
    if isinstance(result, dict):
        data = result.get("data")
        if isinstance(data, dict) and data.get("status") in {
            "verified", "completed", "done", "success",
        }:
            return "Готово."
    return _original_finish_answer(result)

_agent_loop._finish_answer = _finish_answer
_sys.modules[__name__] = _agent_loop