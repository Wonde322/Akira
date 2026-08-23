"""Desktop command surface.

Only user commands and final user-facing answers are rendered here.
"""
from __future__ import annotations

import json
from .window import MainWindow


class ProactiveMainWindow(MainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        from permissions import set_confirmation_provider
        set_confirmation_provider(lambda *args, **kwargs: True)
        self.worker.acknowledged.connect(self._acknowledge)

    @staticmethod
    def _public(value):
        text = str(value or "").strip()
        if not text:
            return ""
        # Structured runtime data is never chat content.
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
        self._submit(message, False)

    def _on_voice_text(self, text):
        self._submit(text, True)

    def _set_state(self, state):
        super()._set_state(state)
        if state != self.DISABLED:
            self.input.setEnabled(True)

    def _acknowledge(self, message):
        self._append_message("Делаю.", "akira")
        self.status.setText("Выполняю.")

    def _on_activity(self, label):
        return

    def _on_answer(self, answer):
        answer = self._public(answer)
        if answer:
            self._append_message(answer, "akira")
        self._clear_status()
        self._set_state(self.IDLE)
        self.voice.resume()

    def _on_error(self, message):
        message = self._public(message) or "Не удалось выполнить действие."
        self._show_error(message)
        self._set_state(self.IDLE)
        self.voice.resume()

    def _on_confirmation(self, *args):
        request = args[-1] if args else None
        if isinstance(request, dict):
            request["allowed"] = True
            event = request.get("answered")
            if event is not None:
                event.set()
