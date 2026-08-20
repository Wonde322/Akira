"""Delivery bridge between the proactive inbox and Akira's live surfaces.

The runtime decides *what* deserves attention. This module decides when an
available surface should receive it. It deliberately contains no Qt code so
the desktop UI, voice UI, or another future client can all use the same
bridge.
"""

from __future__ import annotations

import threading

from event_bus import emit_event
from proactive_inbox import get_proactive_inbox


class ProactiveDelivery:
    def __init__(self, inbox=None, emit=None):
        self._inbox = inbox or get_proactive_inbox()
        self._emit = emit or emit_event
        self._lock = threading.RLock()
        self._pending_questions = {}

    def poll(self, limit=20, on_notify=None, on_question=None):
        """Deliver unread proactive items to the currently available surface.

        Notifications are acknowledged after successful delivery. Questions
        remain pending until ``answer`` is called, which prevents them from
        disappearing before the user responds and also prevents duplicates.
        """
        delivered = []
        items = list(reversed(self._inbox.list(limit=limit, unread_only=True)))
        for item in items:
            item_id = item.get("id")
            action = item.get("action")
            if action == "ask_user":
                with self._lock:
                    if item_id in self._pending_questions:
                        continue
                    self._pending_questions[item_id] = dict(item)
                if on_question is not None:
                    on_question(dict(item))
                delivered.append({"id": item_id, "action": action, "pending": True})
                continue

            if on_notify is not None:
                on_notify(dict(item))
            self._inbox.acknowledge(item_id)
            delivered.append({"id": item_id, "action": action, "pending": False})
        return delivered

    def pending_questions(self):
        with self._lock:
            return [dict(item) for item in self._pending_questions.values()]

    def answer(self, item_id, text):
        text = str(text or "").strip()
        if not text:
            return {"success": False, "error": "empty_answer"}
        with self._lock:
            item = self._pending_questions.pop(str(item_id), None)
        if item is None:
            return {"success": False, "error": "question_not_pending"}

        event = self._emit(
            "proactive.answer",
            {
                "answer": text,
                "question": item.get("message"),
                "inbox_item_id": item.get("id"),
                "question_event_id": item.get("event_id"),
            },
            parent_event_id=item.get("event_id"),
            correlation_id=item.get("event_id") or item.get("id"),
            source="proactive_delivery",
        )
        acknowledgement = self._inbox.acknowledge(item.get("id"))
        return {
            "success": bool(acknowledgement.get("success")),
            "event": event,
            "item": acknowledgement.get("item"),
        }


_delivery = None
_delivery_lock = threading.Lock()


def get_proactive_delivery():
    global _delivery
    if _delivery is None:
        with _delivery_lock:
            if _delivery is None:
                _delivery = ProactiveDelivery()
    return _delivery
