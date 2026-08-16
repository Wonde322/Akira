"""Worker thread: выполняет brain.ask в отдельном потоке и сообщает прогресс."""

import queue
import traceback

from PySide6.QtCore import QThread, Signal

from .activity import activity_label


class BrainWorker(QThread):
    """Очередь запросов + поток, который их обрабатывает.

    Сигналы:
        answer_ready(str)  — итоговый ответ Акиры;
        error(str)         — дружелюбное сообщение об ошибке;
        activity(str)      — короткая подпись текущего действия;
        busy(bool)         — True на время обработки запроса.
    """

    answer_ready = Signal(str)
    error = Signal(str)
    activity = Signal(str)
    busy = Signal(bool)

    def __init__(self, session_id="desktop", parent=None):
        super().__init__(parent)
        self.session_id = session_id
        self._queue = queue.Queue()
        self._stop = False

    def submit(self, message):
        self._queue.put(message)

    def request_stop(self):
        self._stop = True
        self._queue.put(None)

    def run(self):
        import audit
        from brain import ask

        audit.set_activity_hook(self._on_activity)

        try:
            while not self._stop:
                message = self._queue.get()

                if message is None:
                    break

                self.busy.emit(True)

                try:
                    answer = ask(message, session_id=self.session_id)
                    self.answer_ready.emit(answer or "")
                except Exception as error:
                    traceback.print_exc()
                    self.error.emit(_friendly_error(error))

                self.busy.emit(False)
        finally:
            audit.clear_activity_hook()

    def _on_activity(self, tool_name, arguments):
        self.activity.emit(activity_label(tool_name))


def _friendly_error(error):
    text = str(error)

    if "GROQ_API_KEY" in text or "api_key" in text.lower():
        return "Не найден GROQ_API_KEY. Проверь настройки API."

    if "denied" in str(error).lower():
        return "Действие не разрешено."

    return "Не удалось выполнить действие. Попробуй ещё раз."