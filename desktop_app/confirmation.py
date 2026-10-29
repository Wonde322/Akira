"""Thread-safe desktop confirmation bridge."""
from __future__ import annotations
import threading
import time
from PySide6.QtCore import QObject, Signal
from execution_context import current_execution, execution_cancelled


class ConfirmationService(QObject):
    request_received = Signal(str, str, dict, object)

    def __init__(self, parent=None, timeout=30):
        super().__init__(parent); self.timeout=timeout

    @staticmethod
    def _description(tool_name, arguments):
        arguments = arguments or {}
        target = arguments.get("target") or arguments.get("path") or arguments.get("text")
        labels = {"open":"Открыть", "close":"Закрыть", "click":"Кликнуть", "type":"Ввести", "delete":"Удалить", "shell":"Выполнить команду", "write":"Записать"}
        return f"{labels.get(tool_name, tool_name)}: {target}" if target is not None else f"Разрешить: {tool_name}"

    def provider(self, tool_name, arguments):
        if execution_cancelled():
            return False
        request={"tool":tool_name,"arguments":dict(arguments or {}),"allowed":False,"answered":threading.Event()}
        context = current_execution()
        if context is not None:
            request.update(task_id=context.task_id, goal=context.goal)
        self.request_received.emit(tool_name,self._description(tool_name,request["arguments"]),request["arguments"],request)
        deadline = time.monotonic() + self.timeout
        while not request["answered"].is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0 or execution_cancelled():
                request["allowed"] = False
                request["answered"].set()
                return False
            request["answered"].wait(timeout=min(remaining, 0.05))
        return bool(request.get("allowed",False))
