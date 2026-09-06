"""Single-owner desktop request worker."""
from __future__ import annotations

import queue
import threading

from PySide6.QtCore import QThread, Signal

_STOP_WORDS = {"стоп", "остановись", "отмена", "отмени", "хватит", "stop", "cancel"}
_GREETING_WORDS = {"привет", "приветик", "здарова", "здорово", "здравствуй", "хай", "hello", "hi"}


def _simple_greeting(message):
    """Backward-compatible helper; the live worker now routes through Gateway."""
    normalized = str(message or "").strip().casefold().strip(" .,!?:;—-")
    if normalized in _GREETING_WORDS:
        return "Привет."
    if normalized in {"акира", "эй акира", "akira", "hey akira"}:
        return "Да?"
    return None


def _friendly_error(error):
    text = str(error or "").strip()
    lowered = text.casefold()
    if "invalid api key" in lowered or "api key" in lowered or "api_key" in lowered or "groq_api_key" in lowered:
        return "Не удалось обратиться к модели: проверь GROQ_API_KEY."
    if "denied" in lowered or "запрещ" in lowered:
        return "Действие не разрешено."
    return f"Не удалось выполнить запрос: {text}" if text else "Не удалось выполнить запрос."


def _response_text(result):
    if isinstance(result, dict):
        if result.get("response"):
            return str(result["response"])
        if result.get("output"):
            return str(result["output"])
        if result.get("answer"):
            return str(result["answer"])
        if result.get("error"):
            return _friendly_error(result["error"])
    return str(result or "Не получил ответ.")


class BrainWorker(QThread):
    answer_ready = Signal(str)
    error = Signal(str)
    activity = Signal(str)
    busy = Signal(bool)
    acknowledged = Signal(str)

    def __init__(self, session_id="desktop", parent=None):
        super().__init__(parent)
        self.session_id = session_id
        self._queue = queue.Queue()
        self._lock = threading.Lock()
        self._stop = False
        self._stop_event = threading.Event()
        self._generation = 0

    @staticmethod
    def _stop_word(message):
        return str(message or "").strip().casefold().strip(" .,!?:;") in _STOP_WORDS

    def _prepare_start(self):
        with self._lock:
            pending = []
            while True:
                try:
                    item = self._queue.get_nowait()
                except queue.Empty:
                    break
                if item is not None:
                    pending.append(item)
            self._stop = False
            self._stop_event.clear()
            self._generation += 1
            for item in pending:
                self._queue.put(item)

    def submit(self, message):
        if message is None:
            return
        message = str(message).strip()
        if not message:
            return
        with self._lock:
            self._generation += 1
            if self._stop_word(message):
                self._stop = True
                self._stop_event.set()
                self._queue.put(None)
                self.busy.emit(False)
                self.answer_ready.emit("Остановил.")
                return
            self._queue.put(message)

    def cancel_current(self):
        with self._lock:
            self._generation += 1
        self.busy.emit(False)
        return True

    def request_stop(self):
        with self._lock:
            self._generation += 1
            self._stop = True
            self._stop_event.set()
            self._queue.put(None)
        self.busy.emit(False)

    def run(self):
        self._prepare_start()
        while True:
            try:
                message = self._queue.get(timeout=0.1)
            except queue.Empty:
                if self._stop_event.is_set():
                    return
                continue
            if message is None:
                return
            with self._lock:
                generation = self._generation
            self.busy.emit(True)
            try:
                from akira_gateway import create_gateway
                gateway = create_gateway()
                result = gateway.submit_text(message, metadata={"session_id": self.session_id})
                answer = _response_text(result)
            except Exception as exc:
                if generation == self._generation:
                    self.error.emit(_friendly_error(exc))
                    self.busy.emit(False)
                continue
            if generation == self._generation:
                self.answer_ready.emit(answer)
                self.busy.emit(False)
