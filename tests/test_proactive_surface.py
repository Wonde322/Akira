import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from desktop_app.proactive_surface import ProactiveDesktopBridge


class FakeDelivery:
    def __init__(self, items=None):
        self.items = list(items or [])
        self.answers = []

    def poll(self, on_notify=None, on_question=None):
        delivered = []
        for item in list(self.items):
            if item["action"] == "ask_user":
                if on_question:
                    on_question(item)
            elif on_notify:
                on_notify(item)
            delivered.append(item)
        return delivered

    def answer(self, item_id, text):
        self.answers.append((item_id, text))
        return {"success": True, "item_id": item_id, "text": text}


def _app():
    return QApplication.instance() or QApplication([])


def test_desktop_bridge_emits_notifications_and_questions():
    _app()
    delivery = FakeDelivery([
        {"id": "n1", "action": "notify", "message": "done"},
        {"id": "q1", "action": "ask_user", "message": "continue?"},
    ])
    bridge = ProactiveDesktopBridge(delivery=delivery)
    notifications, questions = [], []
    bridge.notification.connect(notifications.append)
    bridge.question.connect(questions.append)

    bridge.poll()

    assert notifications == [{"id": "n1", "action": "notify", "message": "done"}]
    assert questions == [{"id": "q1", "action": "ask_user", "message": "continue?"}]
    assert bridge.active_question_id == "q1"


def test_desktop_bridge_routes_answer_and_reopens_polling():
    _app()
    delivery = FakeDelivery()
    bridge = ProactiveDesktopBridge(delivery=delivery)
    bridge._active_question_id = "q1"

    result = bridge.answer("yes")

    assert result["success"] is True
    assert delivery.answers == [("q1", "yes")]
    assert bridge.active_question_id is None


def test_desktop_bridge_rejects_answer_without_question():
    _app()
    bridge = ProactiveDesktopBridge(delivery=FakeDelivery())

    assert bridge.answer("yes") == {
        "success": False,
        "error": "no_active_question",
    }


def test_multiple_pending_questions_are_presented_in_order(tmp_path):
    from proactive_delivery import ProactiveDelivery
    from proactive_inbox import ProactiveInbox
    _app()
    inbox = ProactiveInbox(path=tmp_path / 'inbox.json')
    inbox.push('first?', action='ask_user')
    inbox.push('second?', action='ask_user')
    delivery = ProactiveDelivery(inbox=inbox, emit=lambda *a, **k: {})
    bridge = ProactiveDesktopBridge(delivery=delivery)
    questions = []
    bridge.question.connect(lambda item: questions.append(item['message']))
    bridge.poll()
    assert questions == ['first?']
    bridge.answer('yes')
    assert questions == ['first?', 'second?']
    bridge.answer('no')
    assert bridge.active_question_id is None
    assert not inbox.list(unread_only=True)


def test_dismissing_question_does_not_emit_an_answer_or_start_work(tmp_path):
    from proactive_delivery import ProactiveDelivery
    from proactive_inbox import ProactiveInbox
    _app()
    inbox = ProactiveInbox(path=tmp_path / 'inbox.json')
    inbox.push('question?', action='ask_user')
    events = []
    delivery = ProactiveDelivery(inbox=inbox, emit=lambda *a, **k: events.append(a))
    bridge = ProactiveDesktopBridge(delivery=delivery)
    bridge.poll()
    assert bridge.dismiss()['success']
    assert not events
    assert not inbox.list(unread_only=True)
    assert bridge.active_question_id is None
