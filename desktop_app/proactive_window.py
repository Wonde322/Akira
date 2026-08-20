"""Main desktop window with live proactive delivery wired into the chat UI."""

from __future__ import annotations

import re

from .proactive_surface import ProactiveDesktopBridge
from .window import MainWindow


class ProactiveMainWindow(MainWindow):
    """MainWindow that routes proactive notifications and answers live."""

    _WAKE_WORDS = {"акира", "akira"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.proactive_surface = ProactiveDesktopBridge(parent=self)
        self.proactive_surface.notification.connect(self._on_proactive_notification)
        self.proactive_surface.question.connect(self._on_proactive_question)
        self.proactive_surface.start()

    @classmethod
    def _is_wake_only(cls, text):
        """Accept only the standalone wake word, with surrounding punctuation."""
        if not isinstance(text, str):
            return False
        match = re.fullmatch(
            r"\s*(?:[^\w\s]*\s*)*([A-Za-zА-Яа-яЁё]+)(?:\s*[^\w\s]*)*\s*",
            text,
        )
        return bool(match and match.group(1).lower() in cls._WAKE_WORDS)

    def _set_state(self, state):
        super()._set_state(state)
        # TTS must never make the chat read-only.
        if state == self.SPEAKING:
            self.input.setEnabled(True)

    def _acknowledge_text_wake(self):
        """A typed wake word must never leave the microphone in dialogue mode."""
        # A queued/stale voice dialogue can otherwise keep recording after a
        # typed wake word and turn later ambient audio into a chat request.
        self.voice.set_dialogue(False)
        self.voice.resume()
        self._set_state(self.IDLE)
        self.status.setText("Слушаю.")
        self.status.setStyleSheet(
            "color: #c0c0c8; font-size: 12px; background: transparent;"
        )
        self.input.setEnabled(True)
        self.input.setFocus()

    def _enter_voice_wake_dialogue(self):
        if not self.voice.is_dialogue():
            self.voice.set_dialogue(True)
        self.voice.resume()
        self._set_state(self.LISTENING)
        self.status.setText("Слушаю.")
        self.status.setStyleSheet(
            "color: #c0c0c8; font-size: 12px; background: transparent;"
        )
        self.input.setEnabled(True)
        self.input.setFocus()

    def _proactive_text(self, item):
        return str(
            item.get("message")
            or item.get("text")
            or item.get("title")
            or ""
        ).strip()

    def _on_proactive_notification(self, item):
        text = self._proactive_text(item)
        if text:
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
        if self._is_wake_only(message):
            self._acknowledge_text_wake()
            return
        if self._state == self.SPEAKING:
            self.voice.stop_speaking()
        if self._submit_proactive_answer(message):
            return
        super()._on_submit(message)

    def _on_voice_text(self, text):
        if not text:
            return
        if self._is_wake_only(text):
            self._enter_voice_wake_dialogue()
            return
        if self._submit_proactive_answer(text):
            self._last_voice = True
            return
        super()._on_voice_text(text)

    def closeEvent(self, event):
        self.proactive_surface.stop()
        super().closeEvent(event)
