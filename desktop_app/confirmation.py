"""Thread-safe desktop confirmation bridge."""
from __future__ import annotations
import threading
from PySide6.QtCore import QObject, Signal


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
        request={"tool":tool_name,"arguments":dict(arguments or {}),"allowed":False,"answered":threading.Event()}
        self.request_received.emit(tool_name,self._description(tool_name,request["arguments"]),request["arguments"],request)
        request["answered"].wait(timeout=self.timeout)
        return bool(request.get("allowed",False))
