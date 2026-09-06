"""Thread-safe desktop confirmation bridge."""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal


class ConfirmationService(QObject):
    request_received = Signal(str, str, dict, object)

    def __init__(self, parent=None, timeout=30):
        super().__init__(parent)
        self.timeout = timeout

    def provider(self, tool_name, arguments):
        request = {
            "tool": tool_name,
            "arguments": dict(arguments or {}),
            "allowed": False,
            "answered": threading.Event(),
        }
        description = f"Разрешить выполнение {tool_name}?"
        self.request_received.emit(tool_name, description, request["arguments"], request)
        request["answered"].wait(timeout=self.timeout)
        return bool(request.get("allowed", False))
