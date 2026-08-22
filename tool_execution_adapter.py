"""
ЭТАП 22/29 — адаптер реального execution boundary проекта.
Автоматически найден: agent_loop.py:execute_tool
"""

from agent_loop import execute_tool as _execute


class ToolExecutionAdapter:

    def execute(self, action, arguments=None):
        arguments = arguments or {}

        attempts = [
            lambda: _execute(action, arguments),
            lambda: _execute(
                action=action,
                arguments=arguments,
            ),
            lambda: _execute(action, **arguments),
            lambda: _execute(**arguments),
        ]

        last_error = None

        for attempt in attempts:
            try:
                return attempt()
            except TypeError as exc:
                last_error = exc

        raise last_error
