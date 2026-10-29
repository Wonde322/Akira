"""Qt bridge for delivering proactive events to the desktop surface.

The bridge owns polling on the UI thread and exposes plain Qt signals.  The
window decides how a notification/question is rendered; this keeps proactive
logic independent from the concrete visual design.
"""

from __future__ import annotations

from collections import deque

from PySide6.QtCore import QObject, QTimer, Signal

from proactive_delivery import get_proactive_delivery


class ProactiveDesktopBridge(QObject):
    notification = Signal(dict)
    question = Signal(dict)

    def __init__(self, delivery=None, interval_ms=1000, parent=None):
        super().__init__(parent)
        self._delivery = delivery or get_proactive_delivery()
        self._timer = QTimer(self)
        self._timer.setInterval(max(100, int(interval_ms)))
        self._timer.timeout.connect(self.poll)
        self._active_question_id = None
        self._queued_questions = deque()

    @property
    def active_question_id(self):
        return self._active_question_id

    def start(self):
        discard = getattr(self._delivery, "discard_startup_notifications", None)
        if callable(discard):
            discard()
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def poll(self):
        return self._delivery.poll(
            on_notify=self._on_notification,
            on_question=self._on_question,
        )

    def _on_notification(self, item):
        self.notification.emit(dict(item))

    def _on_question(self, item):
        if self._active_question_id is not None:
            if item.get("id") != self._active_question_id and not any(q.get("id") == item.get("id") for q in self._queued_questions):
                self._queued_questions.append(dict(item))
            return
        self._active_question_id = item.get("id")
        self.question.emit(dict(item))

    def answer(self, text):
        item_id = self._active_question_id
        if item_id is None:
            return {"success": False, "error": "no_active_question"}
        result = self._delivery.answer(item_id, text)
        return self._advance(result)

    def select(self, proposal_id):
        if self._active_question_id is None:
            return {"success": False, "error": "no_active_question"}
        return self._advance(self._delivery.select(self._active_question_id, proposal_id))

    def dismiss(self):
        if self._active_question_id is None:
            return {"success": False, "error": "no_active_question"}
        return self._advance(self._delivery.dismiss(self._active_question_id))

    def _advance(self, result):
        if result.get("success"):
            self._active_question_id = None
            if self._queued_questions:
                self._on_question(self._queued_questions.popleft())
            else:
                self.poll()
        return result
