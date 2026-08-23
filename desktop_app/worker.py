"""Single-command desktop executor.

There is exactly one active command. A newer command replaces the current one;
old queued commands are discarded and old answers are never shown.
"""
import queue
import threading
import traceback
from PySide6.QtCore import QThread, Signal
from .activity import activity_label

class CommandCancelled(Exception): pass

class BrainWorker(QThread):
    answer_ready=Signal(str); error=Signal(str); activity=Signal(str); busy=Signal(bool); acknowledged=Signal(str)
    def __init__(self,session_id="desktop",parent=None):
        super().__init__(parent); self.session_id=session_id; self._queue=queue.Queue(); self._stop=threading.Event(); self._cancel=threading.Event(); self._lock=threading.RLock(); self._generation=0; self._active=False
    def submit(self,message):
        message=str(message or "").strip()
        if not message:return
        with self._lock:
            replacing=self._active; self._generation+=1; generation=self._generation; self._cancel.set()
            while True:
                try:self._queue.get_nowait()
                except queue.Empty:break
            self._queue.put((generation,message)); self.acknowledged.emit(message)
        if replacing:
            # Clear the old task context immediately. The active turn also sees
            # _cancel at its next tool boundary and cannot continue into another action.
            try:
                from brain import get_session
                get_session(self.session_id).end_task()
            except Exception: pass
    def request_stop(self): self._stop.set(); self._cancel.set(); self._queue.put(None)
    def cancel_current(self):
        with self._lock:
            if not self._active:return False
            self._generation+=1; self._cancel.set()
        try:
            from brain import get_session
            get_session(self.session_id).end_task()
        except Exception:pass
        return True
    def _current(self,generation):
        with self._lock:return generation==self._generation and not self._stop.is_set()
    def run(self):
        import audit
        from brain import ask
        audit.set_activity_hook(self._activity_hook)
        try:
            while not self._stop.is_set():
                item=self._queue.get()
                if item is None:break
                generation,message=item; self._cancel.clear()
                with self._lock:self._active=True
                self.busy.emit(True)
                try:
                    answer=ask(message,session_id=self.session_id)
                    if self._current(generation): self.answer_ready.emit(answer or "Готово.")
                except CommandCancelled: pass
                except Exception as error:
                    if self._current(generation): traceback.print_exc(); self.error.emit(_friendly_error(error))
                finally:
                    with self._lock:self._active=False
                    if self._current(generation): self.busy.emit(False)
        finally:audit.clear_activity_hook()
    def _activity_hook(self,tool_name,arguments):
        if self._cancel.is_set():raise CommandCancelled()
        self.activity.emit(activity_label(tool_name))

def _friendly_error(error):
    text=str(error).casefold()
    if "groq_api_key" in text or "api_key" in text:return "Не найден GROQ_API_KEY."
    return "Не удалось выполнить действие."
