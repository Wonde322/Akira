"""Single foreground-command desktop window.

The previous proactive bridge could inject internal context/task messages into
the same UI used for user commands.  This window intentionally has no
background task surface: one user command enters, one user-facing answer exits.
"""
import json
import re

from .window import MainWindow

_INTERNAL = re.compile(
    r"(?:провер(?:ить|яю)\s+контекст|checking\s+context|\"?(?:evidence|verification|task_id|process_state)\"?\s*:)",
    re.IGNORECASE,
)


class ProactiveMainWindow(MainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Desktop commands are auto-authorized.  Do this after MainWindow has
        # installed its legacy confirmation provider, so that provider cannot
        # create a modal dialog for ordinary execution.
        from permissions import set_confirmation_provider
        set_confirmation_provider(lambda *_args, **_kwargs: True)

        self.worker.acknowledged.connect(self._acknowledge)

    @staticmethod
    def _clean(text):
        text = str(text or "").strip()
        if not text:
            return ""
        if _INTERNAL.search(text):
            return ""
        try:
            value = json.loads(text)
        except Exception:
            return text
        if isinstance(value, (dict, list)):
            return ""
        return text

    def _replace_command(self, message, voice):
        message = self._clean(message)
        if not message:
            return
        if self._state == self.SPEAKING:
            self.voice.stop_speaking()
        self._append_message(message, "user")
        self._last_voice = bool(voice)
        # Never pause the listener while work is running: the next command is
        # allowed to replace this one.
        self.voice.resume()
        self.worker.submit(message)
        self._set_state(self.THINKING)
        self.input.setEnabled(True)

    def _on_submit(self, message):
        self._replace_command(message, False)

    def _on_voice_text(self, text):
        self._replace_command(text, True)

    def _set_state(self, state):
        super()._set_state(state)
        if state != self.DISABLED:
            self.input.setEnabled(True)

    def _on_mic_clicked(self):
        if self._state == self.DISABLED:
            return
        if self._state == self.SPEAKING:
            self.voice.stop_speaking()
        if self._mic_active:
            self.voice.cancel_capture()
            self._set_state(self.IDLE)
            return
        self.voice.capture_once()

    def _acknowledge(self, _message):
        self._append_message("Делаю.", "akira")
        self.status.setText("Выполняю.")

    def _on_activity(self, label):
        label = self._clean(label)
        if label:
            self.status.setText(label)

    def _on_answer(self, answer):
        answer = self._clean(answer) or "Готово."
        self._append_message(answer, "akira")
        self._clear_status()
        self._set_state(self.IDLE)
        # Keep recognition armed after every answer as well.
        self.voice.resume()

    def _on_error(self, message):
        message = self._clean(message) or "Не удалось выполнить действие."
        self._show_error(message)
        self._set_state(self.IDLE)
        self.voice.resume()

    def _on_confirmation(self, *_args):
        # Defensive no-op for legacy UI signals: command execution never waits
        # on a modal confirmation in desktop mode.
        request = _args[-1] if _args else None
        if isinstance(request, dict):
            request["allowed"] = True
            answered = request.get("answered")
            if answered is not None:
                answered.set()
