from proactive_action_execution import ProactiveActionExecutor
from proactive_delivery import ProactiveDelivery
from proactive_inbox import ProactiveInbox


def test_executor_emits_help_request():
    emitted = []
    executor = ProactiveActionExecutor(lambda event_type, payload, **meta: emitted.append((event_type, payload, meta)) or {"type": event_type})
    result = executor.execute({"id": "x", "event_id": "e", "message": "help?", "proposals": [{"id": "help", "kind": "ask"}]}, "help")
    assert result["success"] is True
    assert emitted[0][0] == "proactive.help_requested"
    assert emitted[0][1]["inbox_item_id"] == "x"


def test_executor_rejects_unknown_proposal():
    executor = ProactiveActionExecutor(lambda *args, **kwargs: None)
    result = executor.execute({"proposals": [{"id": "help", "kind": "ask"}]}, "missing")
    assert result == {"success": False, "error": "proposal_not_found"}


def test_delivery_selection_acknowledges_question(tmp_path):
    inbox = ProactiveInbox(tmp_path / "inbox.json")
    item = inbox.push("Нужна помощь?", action="ask_user", proposals=[{"id": "inspect", "kind": "observe"}])
    emitted = []
    delivery = ProactiveDelivery(inbox=inbox, emit=lambda event_type, payload, **meta: emitted.append(event_type) or {"type": event_type})
    delivery.poll()
    result = delivery.select(item["id"], "inspect")
    assert result["success"] is True
    assert emitted == ["proactive.inspect_requested"]
    assert inbox.list(unread_only=True) == []


def test_failed_selection_keeps_question_pending(tmp_path):
    inbox = ProactiveInbox(tmp_path / "inbox.json")
    item = inbox.push("Нужна помощь?", action="ask_user", proposals=[{"id": "help", "kind": "ask"}])
    delivery = ProactiveDelivery(inbox=inbox, emit=lambda *args, **kwargs: {"ok": True})
    delivery.poll()
    result = delivery.select(item["id"], "bad")
    assert result["success"] is False
    assert [value["id"] for value in delivery.pending_questions()] == [item["id"]]
