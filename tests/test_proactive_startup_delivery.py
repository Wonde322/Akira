from desktop_app.proactive_surface import ProactiveDesktopBridge
from proactive_delivery import ProactiveDelivery


class FakeInbox:
    def __init__(self, items):
        self.items = [dict(item) for item in items]
        self.acknowledged = []

    def list(self, limit=20, unread_only=False):
        items = self.items
        if unread_only:
            items = [item for item in items if not item.get("read")]
        return [dict(item) for item in items[-limit:]][::-1]

    def acknowledge(self, item_id):
        self.acknowledged.append(item_id)
        for item in self.items:
            if item.get("id") == item_id:
                item["read"] = True
                return {"success": True, "item": dict(item)}
        return {"success": False}


def test_startup_discards_stale_notifications_but_keeps_questions():
    inbox = FakeInbox([
        {"id": "old-context", "action": "notify", "read": False},
        {"id": "old-question", "action": "ask_user", "read": False},
    ])
    delivery = ProactiveDelivery(inbox=inbox, emit=lambda *args, **kwargs: {})

    discarded = delivery.discard_startup_notifications()

    assert discarded == ["old-context"]
    assert inbox.acknowledged == ["old-context"]
    assert inbox.items[0]["read"] is True
    assert inbox.items[1]["read"] is False


def test_bridge_start_discards_stale_items_before_polling():
    class Delivery:
        def __init__(self):
            self.discarded = 0
            self.polled = 0

        def discard_startup_notifications(self):
            self.discarded += 1

        def poll(self, **kwargs):
            self.polled += 1
            return []

    delivery = Delivery()
    bridge = ProactiveDesktopBridge(delivery=delivery)
    bridge.start()
    bridge.stop()

    assert delivery.discarded == 1
    assert delivery.polled == 0
