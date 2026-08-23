"""Desktop request worker.

Only the newest request is allowed to publish a result.  The worker does not
classify requests, invent status messages, or turn conversation into actions.
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
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._shutdown = threading.Event()
        self._request_id = 0
        self._pending = None

    @staticmethod
    def _is_stop(message):
        return str(message or "").strip().casefold().strip(" .,!?:;") in _STOP_WORDS

    def submit(self, message):
        message = str(message or "").strip()
        if not message:
            return
        is_stop = self._is_stop(message)
        with self._lock:
            self._request_id += 1
            request_id = self._request_id
            self._pending = None if is_stop else (request_id, message)
            self._wake.set()
        if is_stop:
            self.busy.emit(False)
            self.answer_ready.emit("Остановил.")
            return
        if not self.isRunning():
            self.start()

    def cancel_current(self):
        with self._lock:
            self._request_id += 1
            self._pending = None
            self._wake.set()
        self.busy.emit(False)
        return True

    def request_stop(self):
        self.cancel_current()

    def _take_latest(self):
        with self._lock:
            item = self._pending
            self._pending = None
            self._wake.clear()
            return item

    def _is_current(self, request_id):
        with self._lock:
            return request_id == self._request_id

    def _run_request(self, request_id, message):
        try:
            from brain import ask
            answer = ask(message, session_id=self.session_id)
        except Exception:
            traceback.print_exc()
            if self._is_current(request_id):
                self.error.emit("Не удалось выполнить запрос.")
            return
        if self._is_current(request_id):
            self.answer_ready.emit(str(answer or "Готово."))
            self.busy.emit(False)

    def run(self):
        while not self._shutdown.is_set():
            self._wake.wait()
            if self._shutdown.is_set():
                break
            item = self._take_latest()
            if item is None:
                continue
            request_id, message = item
            if not self._is_current(request_id):
                continue
            self.busy.emit(True)
            threading.Thread(
                target=self._run_request,
                args=(request_id, message),
                daemon=True,
                name=f"AkiraRequest-{request_id}",
            ).start()
