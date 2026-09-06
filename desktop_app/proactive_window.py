"""Desktop command surface."""
from __future__ import annotations

import json
import re
from .window import MainWindow


class ProactiveMainWindow(MainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)

    @staticmethod
    def _public(value):
        text = str(value or "").strip()
        if not text:
            return ""
        try:
            parsed = json.loads(text)
            if isinstance(parsed, (dict, list)):
                return ""
        except Exception:
            pass
        lowered = text.casefold()
        if any(token in lowered for token in (
            "проверить контекст", "checking context", "verification", "evidence",
            "process_state", "task_id", "plan_task", "verify_goal",
        )):
            return ""
        return text

    @staticmethod
    def _is_wake_only(text):
        if not isinstance(text, str):
            return False
        normalized = text.strip().casefold()
        normalized = re.sub(r"[.!?,:;]+$", "", normalized).strip()
        return normalized in {"акира", "akira"}

    def _acknowledge_text_wake(self):
        self.voice.set_dialogue(True)
        self.voice.resume()
        self._set_state(self.LISTENING)
        self.input.setEnabled(True)
        self.input.setFocus()

    def _proactive_text(self, payload):
        if not isinstance(payload, dict):
            return self._public(payload)
        return self._public(payload.get("message") or payload.get("title") or "")

    def _submit_proactive_answer(self, text):
        active = getattr(self, "_active_question", None)
        if not active:
            return False
        self._submit(str(text or ""), False)
        self._active_question = None
        return True

    def _submit(self, message, voice=False):
        message = str(message or "").strip()
        if not message:
            return
        if self._state == self.SPEAKING:
            self.voice.stop_speaking()
        self._append_message(message, "user")
        self._last_voice = bool(voice)
        self.input.setEnabled(True)
        self.worker.submit(message)
        self._set_state(self.THINKING)
        self.voice.resume()

    def _on_submit(self, message):
        if self._is_wake_only(message):
            self._acknowledge_text_wake()
            return
        self._submit(message, False)

    def _on_voice_text(self, text):
        self._submit(text, True)

    def _set_state(self, state):
        super()._set_state(state)
        if state != self.DISABLED:
            self.input.setEnabled(True)

    def _on_activity(self, label):
        return

    def _on_answer(self, answer):
        answer = self._public(answer)
        if answer:
            self._append_message(answer, "akira")
        self._clear_status()
        if self._last_voice:
            self._set_state(self.SPEAKING)
            self.voice.speak(answer or "Готово.")
        else:
            self._set_state(self.IDLE)
        self.voice.resume()

    def _on_error(self, message):
        message = self._public(message) or "Не удалось выполнить действие."
        self._show_error(message)
        self._set_state(self.IDLE)
        self.voice.resume()

    def _on_confirmation(self, *args):
        # ConfirmationService owns the decision. This handler intentionally does
        # not auto-approve; UI confirmation can mutate the request and set its
        # event when an explicit answer is received.
        return
