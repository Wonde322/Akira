from proactive_runtime import ProactiveAction, ProactiveRuntime


class FakeInbox:
    def __init__(self):
        self.items = []

    def push(self, message, **kwargs):
        item = {"message": message, **kwargs}
        self.items.append(item)
        return item


def _event(session_id, **payload):
    return {
        "id": "event-1",
        "type": "task.completed",
        "payload": {
            "task_id": "task-1",
            "goal": "Проверить отчёт",
            "session_id": session_id,
            **payload,
        },
    }


def test_proactive_background_completion_notifies_user():
    inbox = FakeInbox()
    runtime = ProactiveRuntime(inbox=inbox)

    result = runtime.handle(_event("proactive:abc123"))

    assert result["decision"]["action"] == ProactiveAction.NOTIFY.value
    assert result["decision"]["reason"] == "proactive_task_completed"
    assert inbox.items[0]["message"] == "Задача завершена: Проверить отчёт"


def test_ordinary_background_completion_stays_quiet_without_opt_in():
    inbox = FakeInbox()
    runtime = ProactiveRuntime(inbox=inbox)

    result = runtime.handle(_event("background:task-1"))

    assert result["decision"]["action"] == ProactiveAction.RECORD.value
    assert inbox.items == []


def test_explicit_completion_notification_still_works():
    inbox = FakeInbox()
    runtime = ProactiveRuntime(inbox=inbox)

    result = runtime.handle(_event("background:task-1", notify=True))

    assert result["decision"]["action"] == ProactiveAction.NOTIFY.value
    assert result["decision"]["reason"] == "background_task_completed"
    assert len(inbox.items) == 1
