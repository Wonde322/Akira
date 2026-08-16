"""Подтверждение действий через GUI.

Провайдер вызывается из потока worker (внутри brain.ask) и должен
остановиться до ответа пользователя. GUI-поток показывает диалог,
устанавливает результат и отпускает событие.
"""

import threading

from PySide6.QtCore import QObject, Signal

from .activity import describe_action


class ConfirmationService(QObject):
    """Мост между confirmation provider (worker thread) и GUI (main thread)."""

    request_received = Signal(str, str, dict, object)

    def __init__(self, parent=None, timeout=600):
        super().__init__(parent)
        self.timeout = timeout

    def provider(self, tool_name, arguments):
        """Вызывается из worker thread внутри request_confirmation.

        Блокируется, пока GUI не ответит (или не истечёт таймаут).
        """
        request = {
            "allowed": False,
            "answered": threading.Event(),
        }

        self.request_received.emit(
            tool_name,
            describe_action(tool_name, arguments),
            arguments,
            request,
        )

        request["answered"].wait(self.timeout)

        return bool(request["allowed"])