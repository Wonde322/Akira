"""Single-owner desktop request worker."""
from __future__ import annotations

import queue
import threading
from collections import deque

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
        if result.get("error"):
            return _friendly_error(result["error"])
    return str(result or "Не получил ответ.")


class BrainWorker(QThread):
    """FIFO request owner with explicit cancellation generations.

    The public queue remains a queue of plain messages for compatibility. A
    parallel generation deque tracks cancellation without changing the queue's
    public contract.
    """

    answer_ready = Signal(str)
    error = Signal(str)
    activity = Signal(str)
    busy = Signal(bool)
    acknowledged = Signal(str)

    def __init__(self, session_id="desktop", parent=None):
        super().__init__(parent)
        self.session_id = session_id
        self._queue = queue.Queue()
        self._generations = deque()
        self._lock = threading.Lock()
        self._stop = False
        self._stop_event = threading.Event()
        self._generation = 0

    def _prepare_start(self):
        with self._lock:
            pending = []
            while True:
                try:
                    message = self._queue.get_nowait()
                except queue.Empty:
                    break
                if message is not None:
                    pending.append(message)

            pending_generations = list(self._generations)
            self._generations.clear()
            self._stop = False
            self._stop_event.clear()

            for index, message in enumerate(pending):
                generation = (
                    pending_generations[index]
                    if index < len(pending_generations)
                    else self._generation
                )
                self._queue.put(message)
                self._generations.append(generation)

    @staticmethod
    def _stop_word(message):
        return str(message or "").strip().casefold().strip(" .,!?:;") in _STOP_WORDS

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
            self._queue.put(message)
            self._generations.append(self._generation)

    def cancel_current(self):
        with self._lock:
            self._generation += 1
        self.busy.emit(False)
        return True

    def request_stop(self):
        with self._lock:
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
                generation = self._generations.popleft() if self._generations else self._generation
            self.busy.emit(True)
            try:
                from akira_gateway import create_gateway
                gateway = create_gateway()
                result = gateway.submit_text(message, metadata={"session_id": self.session_id})
                answer = _response_text(result)
            except Exception as exc:
                with self._lock:
                    current_generation = self._generation
                if generation == current_generation and not self._stop_event.is_set():
                    self.error.emit(_friendly_error(exc))
                self.busy.emit(False)
                continue

            with self._lock:
                current_generation = self._generation
            if generation == current_generation and not self._stop_event.is_set():
                self.answer_ready.emit(answer)
            self.busy.emit(False)
