"""Compatibility facade for Akira's agent runtime.

This module keeps legacy ``brain`` imports pointing at ``agent_loop`` while
installing the runtime policy that separates visual observation from factual
system verification.
"""
import importlib as _importlib
import sys as _sys

import agent_loop as _agent_loop

_agent_loop = _importlib.reload(_agent_loop)

# A screenshot is not the source of truth for process, filesystem or command
# state. Those operations already return authoritative evidence. Only actions
# whose result is inherently visual invalidate visual verification.
_agent_loop.STATE_CHANGING_TOOLS = (
    "click",
    "select",
    "type",
    "scroll",
    "drag",
    "key",
)

_POLICY = """
КРИТИЧЕСКОЕ ПРАВИЛО ПРОВЕРКИ РЕЗУЛЬТАТА:
observe используется только когда для проверки действительно нужны пиксели или
визуальное состояние интерфейса. Не вызывай observe автоматически после open,
close, filesystem или shell, если инструмент уже вернул авторитетное evidence
(process_state, filesystem_state или command_result). Иконка приложения в Dock,
Launchpad или панели не является доказательством запущенного процесса.
Не открывай приложение повторно, если process_state уже подтверждает, что оно
запущено. Не показывай пользователю внутренние результаты observe, JSON,
evidence, task state, "проверку контекста" или другие служебные сообщения.
Пользователь должен получать только нормальный итог выполнения.
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

# Preserve module identity for callers importing either name.
_sys.modules[__name__] = _agent_loop
