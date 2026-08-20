"""Safe execution of explicit proactive action proposals.

The proactive policy may suggest actions, but nothing is executed until the
user explicitly selects one. This module validates the proposal and turns the
selection into a typed event. Concrete workers can subscribe to those events
later without coupling the proactive UI to a particular capability backend.
"""
from __future__ import annotations


class ProactiveActionExecutor:
    EVENT_BY_KIND = {
        "ask": "proactive.help_requested",
        "observe": "proactive.inspect_requested",
        "dismiss": "proactive.dismissed",
    }

    def __init__(self, emit):
        self._emit = emit

    def execute(self, item, proposal_id):
        item = dict(item or {})
        proposal_id = str(proposal_id or "").strip()
        if not proposal_id:
            return {"success": False, "error": "empty_proposal_id"}
        proposals = item.get("proposals") or []
        proposal = next((dict(value) for value in proposals
                         if isinstance(value, dict) and value.get("id") == proposal_id), None)
        if proposal is None:
            return {"success": False, "error": "proposal_not_found"}
        kind = str(proposal.get("kind") or "").strip()
        event_type = self.EVENT_BY_KIND.get(kind)
        if event_type is None:
            return {"success": False, "error": "unsupported_proposal_kind"}
        event = self._emit(
            event_type,
            {
                "proposal_id": proposal_id,
                "proposal": proposal,
                "question": item.get("message"),
                "inbox_item_id": item.get("id"),
                "goal": item.get("goal"),
            },
            parent_event_id=item.get("event_id"),
            correlation_id=item.get("event_id") or item.get("id"),
            source="proactive_action_execution",
        )
        return {"success": True, "proposal": proposal, "event": event}


def get_proactive_action_executor(emit=None):
    if emit is None:
        from event_bus import emit_event
        emit = emit_event
    return ProactiveActionExecutor(emit)
