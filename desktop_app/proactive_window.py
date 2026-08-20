"""Main desktop window with live proactive delivery wired into the chat UI."""

from __future__ import annotations

import json
import re

from .proactive_surface import ProactiveDesktopBridge
from .window import MainWindow


class ProactiveMainWindow(MainWindow):
    _WAKE_WORDS = {"акира", "akira"}
    _INTERNAL_OUTPUT_KEYS = {"status", "evidence", "success", "error", "output", "data"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.proactive_surface = ProactiveDesktopBridge(parent=self)
        self.proactive_surface.notification.connect(self._on_proactive_notification)
        self.proactive_surface.question.connect(self._on_proactive_question)
        self.proactive_surface.start()

    @classmethod
    def _is_wake_only(cls, text):
        if not isinstance(text, str):
            return False
        match = re.fullmatch(
            r"\s*(?:[^\w\s]*\s*)*([A-Za-zА-Яа-яЁё]+)(?:\s*[^\w\s]*)*\s*",
            text,
        )
        return bool(match and match.group(1).lower() in cls._WAKE_WORDS)

    def _set_state(self, state):
        super()._set_state(state)
        if state == self.SPEAKING:
            self.input.setEnabled(True)

    def _acknowledge_text_wake(self):
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

    @classmethod
    def _is_internal_proactive_payload(cls, text):
        """Structured tool/observation output is never user-facing chat text."""
        try:
            value = json.loads(text)
        except (TypeError, ValueError, json.JSONDecodeError):
            return False
        if not isinstance(value, dict):
            return False
        return bool(set(value) & cls._INTERNAL_OUTPUT_KEYS)

    def _proactive_text(self, item):
        text = str(
            item.get("message")
            or item.get("text")
            or item.get("title")
            or ""
        ).strip()
        if not text or self._is_internal_proactive_payload(text):
            return ""
        return text

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

    def _on_answer(self, answer):
        """A completed voice command is one turn: answer, then wake-listening."""
        was_voice = self._last_voice
        if was_voice and self.voice.is_dialogue():
            self.voice.end_turn()
        super()._on_answer(answer)

    def _on_error(self, message):
        if self._last_voice and self.voice.is_dialogue():
            self.voice.end_turn()
        super()._on_error(message)

    def closeEvent(self, event):
        self.proactive_surface.stop()
        super().closeEvent(event)
