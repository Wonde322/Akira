"""Delivery bridge between the proactive inbox and Akira's live surfaces."""
from __future__ import annotations
import threading
from event_bus import emit_event
from proactive_inbox import get_proactive_inbox
from proactive_action_execution import get_proactive_action_executor
from proactive_action_handlers import get_proactive_action_handlers

class ProactiveDelivery:
    def __init__(self, inbox=None, emit=None, action_executor=None, action_handlers=None, feedback_store=None):
        self._inbox = inbox or get_proactive_inbox(); self._emit = emit or emit_event
        self._executor = action_executor or get_proactive_action_executor(self._emit)
        self._handlers = action_handlers
        if feedback_store is None:
            from proactive_feedback import get_proactive_feedback_store
            feedback_store = get_proactive_feedback_store()
        self._feedback_store = feedback_store
        self._lock = threading.RLock(); self._pending_questions = {}
    def poll(self, limit=20, on_notify=None, on_question=None):
        delivered=[]; items=list(reversed(self._inbox.list(limit=limit, unread_only=True)))
        for item in items:
            item_id=item.get("id"); action=item.get("action")
            if action=="ask_user":
                with self._lock:
                    if item_id in self._pending_questions: continue
                    self._pending_questions[item_id]=dict(item)
                if on_question is not None:on_question(dict(item))
                delivered.append({"id":item_id,"action":action,"pending":True}); continue
            if on_notify is not None:on_notify(dict(item))
            self._inbox.acknowledge(item_id); delivered.append({"id":item_id,"action":action,"pending":False})
        return delivered
    def pending_questions(self):
        with self._lock:return [dict(item) for item in self._pending_questions.values()]
    def _take_pending(self,item_id):
        with self._lock:return self._pending_questions.pop(str(item_id),None)
    def answer(self,item_id,text):
        text=str(text or "").strip()
        if not text:return {"success":False,"error":"empty_answer"}
        item=self._take_pending(item_id)
        if item is None:return {"success":False,"error":"question_not_pending"}
        event=self._emit("proactive.answer",{"answer":text,"question":item.get("message"),"inbox_item_id":item.get("id"),"question_event_id":item.get("event_id")},parent_event_id=item.get("event_id"),correlation_id=item.get("event_id") or item.get("id"),source="proactive_delivery")
        acknowledgement=self._inbox.acknowledge(item.get("id")); return {"success":bool(acknowledgement.get("success")),"event":event,"item":acknowledgement.get("item")}
    def select(self,item_id,proposal_id):
        key=str(item_id)
        with self._lock:item=self._pending_questions.get(key)
        if item is None:return {"success":False,"error":"question_not_pending"}
        proposals=item.get("proposals") or []
        proposal=next((candidate for candidate in proposals if str(candidate.get("id"))==str(proposal_id)),None)
        result=self._executor.execute(item,proposal_id)
        if not result.get("success"):return result
        if proposal is not None:
            result["feedback"]=self._feedback_store.record(item.get("reason"),proposal.get("kind"))
        if self._handlers is not None:
            handled=self._handlers.handle(result.get("event"))
            result["execution"]=handled
            if handled.get("handled") and not handled.get("success",False):return {**result,"success":False,"error":"action_handler_failed"}
        with self._lock:self._pending_questions.pop(key,None)
        acknowledgement=self._inbox.acknowledge(item.get("id")); result["item"]=acknowledgement.get("item"); return result

_delivery=None; _delivery_lock=threading.Lock()
def get_proactive_delivery():
    global _delivery
    if _delivery is None:
        with _delivery_lock:
            if _delivery is None:_delivery=ProactiveDelivery(action_handlers=get_proactive_action_handlers())
    return _delivery
