"""Latest-command desktop worker.

Commands are never queued. Each execution runs independently so a new command or
`stop` is accepted immediately; results from superseded executions are discarded.
"""
from __future__ import annotations

import threading
import traceback
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
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._generation = 0
        self._message = ""
        self._active_generation = None

    @staticmethod
    def _is_stop(message):
        return str(message or "").strip().casefold().strip(".!?,:;") in _STOP_WORDS

    def submit(self, message):
        message = str(message or "").strip()
        if not message:
            return
        with self._lock:
            self._generation += 1
            generation = self._generation
            self._message = "" if self._is_stop(message) else message
            self._active_generation = None if self._is_stop(message) else generation
            self._wake.set()
        if self._is_stop(message):
            self.busy.emit(False)
            self.answer_ready.emit("Остановил.")
        else:
            self.acknowledged.emit(message)
        if not self.isRunning():
            self.start()

    def request_stop(self):
        with self._lock:
            self._generation += 1
            self._message = ""
            self._active_generation = None
            self._stop.set()
            self._wake.set()
        self.busy.emit(False)

    def cancel_current(self):
        with self._lock:
            self._generation += 1
            self._message = ""
            self._active_generation = None
            self._wake.set()
        self.busy.emit(False)
        return True

    def _take(self):
        with self._lock:
            generation = self._generation
            message = self._message
            self._message = ""
            self._wake.clear()
        return generation, message

    def _current(self, generation):
        with self._lock:
            return generation == self._generation and not self._stop.is_set()

    def _execute(self, generation, message):
        try:
            from brain import ask
            answer = ask(message, session_id=self.session_id)
            if self._current(generation):
                self.answer_ready.emit(str(answer or "Готово."))
        except Exception:
            traceback.print_exc()
            if self._current(generation):
                self.error.emit("Не удалось выполнить действие.")
        finally:
            if self._current(generation):
                with self._lock:
                    if self._active_generation == generation:
                        self._active_generation = None
                self.busy.emit(False)

    def run(self):
        while not self._stop.is_set():
            self._wake.wait()
            if self._stop.is_set():
                break
            generation, message = self._take()
            if not message:
                continue
            if self._current(generation):
                self.busy.emit(True)
                threading.Thread(
                    target=self._execute,
                    args=(generation, message),
                    daemon=True,
                    name=f"AkiraCommand-{generation}",
                ).start()
