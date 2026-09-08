"""Single-owner desktop request worker."""
from __future__ import annotations

import queue
import threading
import uuid

from PySide6.QtCore import QThread, Signal

_STOP_WORDS = {"стоп", "остановись", "отмена", "отмени", "хватит", "stop", "cancel"}
_GREETING_WORDS = {"привет", "приветик", "здарова", "здорово", "здравствуй", "хай", "hello", "hi"}


def _simple_greeting(message):
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
        for key in ("response", "output", "answer"):
            if result.get(key):
                return str(result[key])
        if result.get("error") == "cancelled":
            return ""
        if result.get("error"):
            return _friendly_error(result["error"])
    return str(result or "Не получил ответ.")


class BrainWorker(QThread):
    """Own the desktop FIFO and cancel the active runtime request cooperatively."""

    answer_ready = Signal(str)
    error = Signal(str)
    activity = Signal(str)
    busy = Signal(bool)
    acknowledged = Signal(str)

    def __init__(self, session_id="desktop", parent=None):
        super().__init__(parent)
        self.session_id = session_id
        self._queue = queue.Queue()
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._active_request_id = None
        self._gateway = None

    @staticmethod
    def _stop_word(message):
        return str(message or "").strip().casefold().strip(" .,!?:;") in _STOP_WORDS

    def _gateway_instance(self):
        if self._gateway is None:
            from akira_gateway import create_gateway
            self._gateway = create_gateway()
        return self._gateway

    def submit(self, message):
        if message is None:
            return
        message = str(message).strip()
        if not message:
            return
        if self._stop_word(message):
            self.cancel_current()
            self.answer_ready.emit("Остановил.")
            return
        with self._lock:
            if self._stop_event.is_set():
                return
            self._queue.put((message, str(uuid.uuid4())))

    def cancel_current(self):
        with self._lock:
            request_id = self._active_request_id
        if not request_id:
            return False
        return bool(self._gateway_instance().cancel(request_id))

    def request_stop(self):
        with self._lock:
            self._stop_event.set()
            request_id = self._active_request_id
            while True:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break
        if request_id:
            self._gateway_instance().cancel(request_id)
        if not self.isRunning():
            return
        self._queue.put(None)

    def run(self):
        self._stop_event.clear()
        while True:
            try:
                item = self._queue.get(timeout=0.1)
            except queue.Empty:
                if self._stop_event.is_set():
                    return
                continue

            if item is None:
                return

            message, request_id = item
            with self._lock:
                if self._stop_event.is_set():
                    continue
                self._active_request_id = request_id
            self.busy.emit(True)

            try:
                result = self._gateway_instance().submit_text(
                    message,
                    metadata={"session_id": self.session_id},
                    request_id=request_id,
                )
                answer = _response_text(result)
                with self._lock:
                    cancelled = self._stop_event.is_set() or self._active_request_id != request_id
                if not cancelled and answer:
                    self.answer_ready.emit(answer)
            except Exception as exc:
                with self._lock:
                    cancelled = self._stop_event.is_set() or self._active_request_id != request_id
                if not cancelled:
                    self.error.emit(_friendly_error(exc))
            finally:
                with self._lock:
                    if self._active_request_id == request_id:
                        self._active_request_id = None
                self.busy.emit(False)
