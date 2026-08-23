"""One-command desktop worker.

A newer command always supersedes the older command. The worker keeps no task
plan and no queue of historical commands.
"""
from __future__ import annotations

import threading
import traceback
from PySide6.QtCore import QThread, Signal


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
        self._active = False

    def submit(self, message):
        message = str(message or "").strip()
        if not message:
            return
        with self._lock:
            self._generation += 1
            self._message = message
            self._wake.set()
        self.acknowledged.emit(message)
        if not self.isRunning():
            self.start()

    def request_stop(self):
        self._stop.set()
        self._wake.set()

    def cancel_current(self):
        with self._lock:
            if not self._active:
                return False
            self._generation += 1
            self._message = ""
        return True

    def _take(self):
        with self._lock:
            generation = self._generation
            message = self._message
            self._message = ""
            self._wake.clear()
            self._active = bool(message)
        return generation, message

    def _current(self, generation):
        with self._lock:
            return generation == self._generation and not self._stop.is_set()

    def run(self):
        from brain import ask
        while not self._stop.is_set():
            self._wake.wait()
            if self._stop.is_set():
                break
            generation, message = self._take()
            if not message:
                continue
            if self._current(generation):
                self.busy.emit(True)
            try:
                answer = ask(message, session_id=self.session_id)
                if self._current(generation):
                    self.answer_ready.emit(str(answer or "Готово."))
            except Exception:
                traceback.print_exc()
                if self._current(generation):
                    self.error.emit("Не удалось выполнить действие.")
            finally:
                with self._lock:
                    if generation == self._generation:
                        self._active = False
                if self._current(generation):
                    self.busy.emit(False)
