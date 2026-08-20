"""Main desktop window with live proactive delivery wired into the chat UI."""

from __future__ import annotations

from .proactive_surface import ProactiveDesktopBridge
from .window import MainWindow


class ProactiveMainWindow(MainWindow):
    """MainWindow that routes proactive notifications and answers live.

    Normal user messages still go to ``BrainWorker``.  While Akira has an
    active proactive question, the next submitted message is instead routed
    through ``ProactiveDelivery.answer`` so it continues the original event
    chain rather than becoming an unrelated chat request.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.proactive_surface = ProactiveDesktopBridge(parent=self)
        self.proactive_surface.notification.connect(self._on_proactive_notification)
        self.proactive_surface.question.connect(self._on_proactive_question)
        self.proactive_surface.start()

    def _proactive_text(self, item):
        return str(
            item.get("message")
            or item.get("text")
            or item.get("title")
            or ""
        ).strip()

    def _on_proactive_notification(self, item):
        text = self._proactive_text(item)
        if not text:
            return
        self._append_message(text, "akira")

    def _on_proactive_question(self, item):
        text = self._proactive_text(item)
        if not text:
            return
        self._append_message(text, "akira")
        self.status.setText("Акира ждёт ответа.")
        self.status.setStyleSheet(
            "color: #c0c0c8; font-size: 12px; background: transparent;"
        )
        self.input.setEnabled(True)
        self.input.setFocus()

    def _submit_proactive_answer(self, message):
        if self.proactive_surface.active_question_id is None:
            return False
        self._append_message(message, "user")
        result = self.proactive_surface.answer(message)
        if result.get("success"):
            self._clear_status()
            if self.voice.is_dialogue():
                self._set_state(self.LISTENING)
                self.voice.resume()
            else:
                self._set_state(self.IDLE)
        else:
            self._show_error("Не удалось передать ответ Акире.")
        return True

    def _on_submit(self, message):
        if self._submit_proactive_answer(message):
            return
        super()._on_submit(message)

    def _on_voice_text(self, text):
        if not text:
            return
        if self._submit_proactive_answer(text):
            self._last_voice = True
            return
        super()._on_voice_text(text)

    def closeEvent(self, event):
        self.proactive_surface.stop()
        super().closeEvent(event)
