from proactive_delivery import ProactiveDelivery
from proactive_inbox import ProactiveInbox


class FakeFeedback:
    def __init__(self): self.records = []
    def record(self, reason, kind):
        self.records.append((reason, kind))
        return {"reason": reason, "kind": kind}


def make_delivery(tmp_path):
    inbox = ProactiveInbox(tmp_path / "inbox.json")
    feedback = FakeFeedback()
    delivery = ProactiveDelivery(
        inbox=inbox,
        feedback_store=feedback,
        emit=lambda event_type, payload, **meta: {"type": event_type},
    )
    return inbox, feedback, delivery


def test_select_records_dismiss_feedback(tmp_path):
    inbox, feedback, delivery = make_delivery(tmp_path)
    item = inbox.push("Вмешаться?", action="ask_user", reason="repeated_task_context", proposals=[{"id": "continue", "kind": "dismiss"}])
    delivery.poll()
    result = delivery.select(item["id"], "continue")
    assert result["success"] is True
    assert feedback.records == [("repeated_task_context", "dismiss")]


def test_select_records_help_as_accepted_feedback(tmp_path):
    inbox, feedback, delivery = make_delivery(tmp_path)
    item = inbox.push("Помочь?", action="ask_user", reason="repeated_task_context", proposals=[{"id": "help", "kind": "ask"}])
    delivery.poll()
    result = delivery.select(item["id"], "help")
    assert result["success"] is True
    assert feedback.records == [("repeated_task_context", "ask")]


def test_invalid_selection_does_not_record_feedback(tmp_path):
    inbox, feedback, delivery = make_delivery(tmp_path)
    item = inbox.push("Помочь?", action="ask_user", reason="repeated_task_context", proposals=[{"id": "help", "kind": "ask"}])
    delivery.poll()
    result = delivery.select(item["id"], "missing")
    assert result["success"] is False
    assert feedback.records == []
