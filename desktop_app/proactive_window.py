"""Main desktop window with live proactive delivery wired into the chat UI."""

from __future__ import annotations

import json
import re

from .proactive_surface import ProactiveDesktopBridge
from .window import MainWindow


class ProactiveMainWindow(MainWindow):
    _WAKE_WORDS = {"акира", "akira"}
    _INTERNAL_OUTPUT_KEYS = {"status", "evidence", "success", "error", "output", "data", "verification"}
    _LEGACY_TEST_MESSAGES = {"готово: проверить контекст", "готово: x", "ok"}
    _INTERNAL_TEXT = {"проверяю контекст", "проверка контекста", "checking context", "checking current context"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker.acknowledged.connect(self._on_command_acknowledged)
        self.proactive_surface = ProactiveDesktopBridge(parent=self)
        self.proactive_surface.notification.connect(self._on_proactive_notification)
        self.proactive_surface.question.connect(self._on_proactive_question)
        self.proactive_surface.start()

    @classmethod
    def _is_wake_only(cls, text):
        if not isinstance(text, str):
            return False
        match = re.fullmatch(r"\s*(?:[^\w\s]*\s*)*([A-Za-zА-Яа-яЁё]+)(?:\s*[^\w\s]*)*\s*", text)
        return bool(match and match.group(1).lower() in cls._WAKE_WORDS)

    def _set_state(self, state):
        super()._set_state(state)
        # The user must always be able to replace a running task. Thinking is
        # not an input lock and must never disable the microphone/text path.
        if state in (self.SPEAKING, self.THINKING, self.LISTENING, self.IDLE):
            self.input.setEnabled(True)

    def _acknowledge_text_wake(self):
        self.voice.set_dialogue(False)
        self.voice.resume()
        self._set_state(self.IDLE)
        self.status.setText("Слушаю.")
        self.status.setStyleSheet("color: #c0c0c8; font-size: 12px; background: transparent;")
        self.input.setEnabled(True)
        self.input.setFocus()

    def _enter_voice_wake_dialogue(self):
        if not self.voice.is_dialogue():
            self.voice.set_dialogue(True)
        self.voice.resume()
        self._set_state(self.LISTENING)
        self.status.setText("Слушаю.")
        self.status.setStyleSheet("color: #c0c0c8; font-size: 12px; background: transparent;")
        self.input.setEnabled(True)
        self.input.setFocus()

    @classmethod
    def _is_internal_proactive_payload(cls, text):
        normalized = str(text).casefold().strip()
        if normalized in cls._LEGACY_TEST_MESSAGES or normalized in cls._INTERNAL_TEXT:
            return True
        try:
            value = json.loads(str(text))
        except (TypeError, ValueError, json.JSONDecodeError):
            return False
        return isinstance(value, dict) and bool(set(value) & cls._INTERNAL_OUTPUT_KEYS)

    @classmethod
    def _sanitize_answer(cls, answer):
        text = str(answer or "").strip()
        if not text:
            return ""
        if cls._is_internal_proactive_payload(text):
            return "Готово."
        return text

    def _proactive_text(self, item):
        text = str(item.get("message") or item.get("text") or item.get("title") or "").strip()
        if not text or ProactiveMainWindow._is_internal_proactive_payload(text):
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
        self.status.setStyleSheet("color: #c0c0c8; font-size: 12px; background: transparent;")
        self.input.setEnabled(True)
        self.input.setFocus()

    def _submit_proactive_answer(self, message):
        if self.proactive_surface.active_question_id is None:
            return False
        self._append_message(message, "user")
        result = self.proactive_surface.answer(message)
        if result.get("success"):
            self._clear_status()
            self.voice.resume()
            self._set_state(self.LISTENING if self.voice.is_dialogue() else self.IDLE)
        else:
            self._show_error("Не удалось передать ответ Акире.")
        return True

    def _on_command_acknowledged(self, message):
        # Immediate acknowledgement makes command replacement visible instead
        # of leaving the user staring at an unresponsive observation/task.
        self._append_message("Делаю.", "akira")
        self.status.setText("Выполняю новую команду.")
        self.status.setStyleSheet("color: #c0c0c8; font-size: 12px; background: transparent;")

    def _submit_to_worker(self, message, *, voice=False):
        self._append_message(message, "user")
        self._last_voice = bool(voice)
        self.worker.submit(message)
        # Recording stays armed while the worker or a tool is busy, so a new
        # voice command can replace the current one.
        self.voice.resume()
        self._set_state(self.THINKING)

    def _on_submit(self, message):
        if self._is_wake_only(message):
            self._acknowledge_text_wake()
            return
        if self._state == self.SPEAKING:
            self.voice.stop_speaking()
        if self._submit_proactive_answer(message):
            return
        self._submit_to_worker(message, voice=False)

    def _on_voice_text(self, text):
        if not text:
            return
        if self._is_wake_only(text):
            self._enter_voice_wake_dialogue()
            return
        if self._submit_proactive_answer(text):
            self._last_voice = True
            self.voice.resume()
            return
        self._submit_to_worker(text, voice=True)

    def _on_answer(self, answer):
        answer = self._sanitize_answer(answer) or "Готово."
        was_voice = self._last_voice
        if was_voice and self.voice.is_dialogue():
            self.voice.end_turn()
        super()._on_answer(answer)

    def _on_error(self, message):
        if self._last_voice and self.voice.is_dialogue():
            self.voice.end_turn()
        super()._on_error(message)
        self.voice.resume()

    def _on_activity(self, label):
        text = str(label or "").strip()
        if text.casefold() in self._INTERNAL_TEXT:
            return
        super()._on_activity(text)

    def _on_mic_clicked(self):
        # Unlike the old base implementation, THINKING is interruptible: the
        # mic remains usable and the next recognized command replaces the task.
        if self._state == self.DISABLED:
            return
        if self._state == self.SPEAKING:
            self.voice.stop_speaking()
        if self._mic_active:
            self.voice.cancel_capture()
            self._set_state(self.IDLE)
            return
        self.voice.capture_once()

    def closeEvent(self, event):
        self.proactive_surface.stop()
        super().closeEvent(event)