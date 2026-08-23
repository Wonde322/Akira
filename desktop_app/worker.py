"""Worker thread: executes brain.ask and gives the newest user command priority."""

import queue
import threading
import traceback

from PySide6.QtCore import QThread, Signal

from .activity import activity_label


class AgentCancelled(Exception):
    """Raised at a safe execution boundary after the user interrupts a task."""


class BrainWorker(QThread):
    """Queue-backed brain worker with cooperative latest-command cancellation.

    Ordinary user commands are replacement commands: a new request interrupts
    the active turn and drops older queued requests. Only explicit "continue"
    requests preserve the current task. This prevents stale actions from being
    executed after the user has already changed their mind.
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
        self._stop = False
        self._cancel_event = threading.Event()
        self._active = False
        self._interrupt_preserves_task = False
        self._suppress_interrupt_notice = False
        self._state_lock = threading.Lock()

    def _prepare_start(self):
        pending = []
        while True:
            try:
                message = self._queue.get_nowait()
            except queue.Empty:
                break
            if message is not None:
                pending.append(message)
        self._queue = queue.Queue()
        for message in pending:
            self._queue.put(message)
        self._stop = False
        self._cancel_event.clear()
        with self._state_lock:
            self._active = False

    def start(self, priority=QThread.Priority.InheritPriority):
        if self.isRunning():
            return
        self._prepare_start()
        super().start(priority)

    def _drop_pending(self):
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                return

    def submit(self, message):
        if message is None:
            return
        message = str(message).strip()
        if not message:
            return

        text = message.lower()
        resume = text in {"продолжай", "продолжи", "продолжить", "resume", "continue"}
        with self._state_lock:
            active = self._active

        if not resume:
            # Latest command wins. Do not execute a backlog of obsolete voice
            # commands after an interruption.
            self._drop_pending()
            if active:
                self._interrupt_preserves_task = False
                self._suppress_interrupt_notice = True
                self._cancel_event.set()
            self.acknowledged.emit(message)
        elif active:
            self._interrupt_preserves_task = True
            self._suppress_interrupt_notice = True
            self._cancel_event.set()

        self._queue.put(message)

    def request_stop(self):
        self._stop = True
        self._cancel_event.set()
        self._drop_pending()
        self._queue.put(None)

    def cancel_current(self):
        with self._state_lock:
            active = self._active
        if not active:
            return False
        self._interrupt_preserves_task = False
        self._suppress_interrupt_notice = False
        self._cancel_event.set()
        return True

    def run(self):
        import audit
        from brain import ask

        audit.set_activity_hook(self._on_activity)
        try:
            while not self._stop:
                message = self._queue.get()
                if message is None:
                    break

                self._cancel_event.clear()
                self._interrupt_preserves_task = False
                self._suppress_interrupt_notice = False
                with self._state_lock:
                    self._active = True
                self.busy.emit(True)

                try:
                    answer = ask(message, session_id=self.session_id)
                    if self._cancel_event.is_set():
                        raise AgentCancelled()
                    self.answer_ready.emit(answer or "")
                except AgentCancelled:
                    if not self._interrupt_preserves_task:
                        from brain import get_session
                        get_session(self.session_id).end_task()
                    if not self._suppress_interrupt_notice:
                        self.answer_ready.emit("Остановил текущую задачу.")
                except Exception as error:
                    traceback.print_exc()
                    self.error.emit(_friendly_error(error))
                finally:
                    with self._state_lock:
                        self._active = False
                    self.busy.emit(False)
        finally:
            audit.clear_activity_hook()

    def _on_activity(self, tool_name, arguments):
        if self._cancel_event.is_set():
            raise AgentCancelled()
        self.activity.emit(activity_label(tool_name))


def _friendly_error(error):
    text = str(error)
    if "GROQ_API_KEY" in text or "api_key" in text.lower():
        return "Не найден GROQ_API_KEY. Проверь настройки API."
    if "denied" in text.lower():
        return "Действие не разрешено."
    return "Не удалось выполнить действие. Попробуй ещё раз."