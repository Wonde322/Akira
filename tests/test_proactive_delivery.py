from proactive_delivery import ProactiveDelivery
from proactive_inbox import ProactiveInbox


def test_notification_is_delivered_and_acknowledged(tmp_path):
    inbox = ProactiveInbox(tmp_path / "inbox.json")
    item = inbox.push("Task failed", action="notify")
    seen = []
    delivery = ProactiveDelivery(inbox=inbox, emit=lambda *a, **k: {"success": True})

    delivered = delivery.poll(on_notify=lambda value: seen.append(value))

    assert seen[0]["id"] == item["id"]
    assert delivered[0]["pending"] is False
    assert inbox.list(unread_only=True) == []


def test_question_stays_pending_until_answer(tmp_path):
    inbox = ProactiveInbox(tmp_path / "inbox.json")
    item = inbox.push("Continue?", action="ask_user", event={"id": "evt-1"})
    seen = []
    delivery = ProactiveDelivery(inbox=inbox, emit=lambda *a, **k: {"success": True})

    delivery.poll(on_question=lambda value: seen.append(value))
    delivery.poll(on_question=lambda value: seen.append(value))

    assert len(seen) == 1
    assert delivery.pending_questions()[0]["id"] == item["id"]
    assert inbox.list(unread_only=True)[0]["id"] == item["id"]


def test_answer_emits_correlated_event_and_acknowledges(tmp_path):
    inbox = ProactiveInbox(tmp_path / "inbox.json")
    item = inbox.push("Which file?", action="ask_user", event={"id": "evt-9"})
    calls = []

    def emit(*args, **kwargs):
        calls.append((args, kwargs))
        return {"success": True, "event": {"id": "answer-1"}}

    delivery = ProactiveDelivery(inbox=inbox, emit=emit)
    delivery.poll(on_question=lambda value: None)
    result = delivery.answer(item["id"], "README.md")

    assert result["success"] is True
    assert calls[0][0][0] == "proactive.answer"
    assert calls[0][0][1]["answer"] == "README.md"
    assert calls[0][1]["parent_event_id"] == "evt-9"
    assert inbox.list(unread_only=True) == []


def test_empty_or_unknown_answer_is_rejected(tmp_path):
    inbox = ProactiveInbox(tmp_path / "inbox.json")
    delivery = ProactiveDelivery(inbox=inbox, emit=lambda *a, **k: {"success": True})

    assert delivery.answer("missing", "") == {"success": False, "error": "empty_answer"}
    assert delivery.answer("missing", "yes") == {"success": False, "error": "question_not_pending"}
