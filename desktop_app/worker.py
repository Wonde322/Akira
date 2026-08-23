"""Single-owner desktop request worker."""
from __future__ import annotations

import threading
from PySide6.QtCore import QThread, Signal

_STOP_WORDS = {"стоп", "остановись", "отмена", "отмени", "хватит", "stop", "cancel"}


class BrainWorker(QThread):
    answer_ready = Signal(str)
    error = Signal(str)
    activity = Signal(str)
    busy = Signal(bool)
    acknowledged = Signal(str)

    def __init__(self, session_id="desktop", parent=None):
        super().__init__(parent)
        self.session_id = session_id
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._shutdown = threading.Event()
        self._generation = 0
        self._pending = None

    @staticmethod
    def _stop_word(message):
        return str(message or "").strip().casefold().strip(" .,!?:;") in _STOP_WORDS

    def submit(self, message):
        message = str(message or "").strip()
        if not message:
            return
        with self._lock:
            self._generation += 1
            generation = self._generation
            if self._stop_word(message):
                self._pending = None
                self._wake.set()
                self.busy.emit(False)
                self.answer_ready.emit("Остановил.")
                return
            self._pending = (generation, message)
            self._wake.set()
        if not self.isRunning():
            self.start()

    def cancel_current(self):
        with self._lock:
            self._generation += 1
            self._pending = None
        self.busy.emit(False)
        return True

    request_stop = cancel_current

    def _next(self):
        with self._lock:
            item = self._pending
            self._pending = None
            self._wake.clear()
            return item

    def _current(self, generation):
        with self._lock:
            return generation == self._generation

    def run(self):
        while not self._shutdown.is_set():
            self._wake.wait()
            if self._shutdown.is_set():
                return
            item = self._next()
            if item is None:
                continue
            generation, message = item
            if not self._current(generation):
                continue
            self.busy.emit(True)
            try:
                from brain import ask
                answer = ask(message, session_id=self.session_id)
            except Exception as exc:
                if self._current(generation):
                    self.error.emit(f"Ошибка: {exc}")
                    self.busy.emit(False)
                continue
            if self._current(generation):
                self.answer_ready.emit(str(answer or "Не получил ответ."))
                self.busy.emit(False)
