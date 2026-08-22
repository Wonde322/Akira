from proactive_runtime import ProactiveRuntime


class _Inbox:
    def __init__(self):
        self.items = []

    def push(self, message, **kwargs):
        item = {"message": message, **kwargs}
        self.items.append(item)
        return item


class _Budget:
    def allow(self, *args, **kwargs):
        return True


def test_regular_background_completion_notifies_user():
    inbox = _Inbox()
    runtime = ProactiveRuntime(inbox=inbox, attention_budget=_Budget())
    event = {
        "id": "background-complete-1",
        "type": "task.completed",
        "payload": {
            "task_id": "task-1",
            "goal": "найти варианты квартир",
            "result": "Найдено 5 вариантов.",
            "session_id": "background:task-1",
        },
    }

    result = runtime.handle(event)

    assert result["decision"]["action"] == "notify"
    assert result["decision"]["reason"] == "background_task_completed"
    assert len(inbox.items) == 1
    assert "Найдено 5 вариантов." in inbox.items[0]["message"]


def test_proactive_completion_keeps_proactive_reason():
    inbox = _Inbox()
    runtime = ProactiveRuntime(inbox=inbox, attention_budget=_Budget())
    event = {
        "id": "proactive-complete-1",
        "type": "task.completed",
        "payload": {
            "task_id": "task-2",
            "goal": "проверить обновления",
            "result": "Есть изменения.",
            "session_id": "proactive:correlation-1",
        },
    }

    result = runtime.handle(event)

    assert result["decision"]["action"] == "notify"
    assert result["decision"]["reason"] == "proactive_task_completed"
