from proactive_inbox import ProactiveInbox
from proactive_runtime import ProactiveAction, ProactiveRuntime
from awareness import AwarenessRuntime


def event(event_type, payload=None, **metadata):
    return {"id": "evt-1", "type": event_type, "payload": payload or {}, **metadata}


def test_task_failure_becomes_high_priority_notification(tmp_path):
    inbox = ProactiveInbox(tmp_path / "inbox.json")
    runtime = ProactiveRuntime(inbox=inbox)
    result = runtime.handle(event("task.failed", {"goal": "проверить почту", "error": "network"}))
    assert result["decision"]["action"] == ProactiveAction.NOTIFY.value
    assert result["decision"]["priority"] == "high"
    assert result["attention"]["message"].startswith("Не удалось завершить задачу")
    assert inbox.list()[0]["event_type"] == "task.failed"


def test_question_becomes_persistent_ask_user_item(tmp_path):
    inbox = ProactiveInbox(tmp_path / "inbox.json")
    runtime = ProactiveRuntime(inbox=inbox)
    result = runtime.handle(event("proactive.question", {"question": "Продолжить работу?"}))
    assert result["decision"]["action"] == ProactiveAction.ASK_USER.value
    item = inbox.list()[0]
    assert item["message"] == "Продолжить работу?"
    acknowledged = inbox.acknowledge(item["id"])
    assert acknowledged["success"] is True
    assert acknowledged["item"]["read"] is True


def test_completed_task_notifies_only_when_requested(tmp_path):
    inbox = ProactiveInbox(tmp_path / "inbox.json")
    runtime = ProactiveRuntime(inbox=inbox, dedupe_seconds=0)
    silent = runtime.handle(event("task.completed", {"goal": "тихая задача"}))
    assert silent["decision"]["action"] == ProactiveAction.RECORD.value
    notified = runtime.handle(event("task.completed", {"goal": "важная задача", "notify": True}, id="evt-2"))
    assert notified["decision"]["action"] == ProactiveAction.NOTIFY.value
    assert inbox.list()[0]["message"] == "Задача завершена: важная задача"


def test_desktop_change_reason_contains_changed_fields():
    runtime = ProactiveRuntime(dedupe_seconds=0)
    decision = runtime.decide(event("desktop.changed", {"changed_fields": ["ui"]}))
    assert decision.action == ProactiveAction.RECORD
    assert decision.reason == "desktop_changed:ui"


def test_awareness_changed_fields_is_structural():
    previous = {"screen": {"width": 100}, "ui": {"app": "A"}}
    current = {"screen": {"width": 100}, "ui": {"app": "B"}}
    assert AwarenessRuntime._changed_fields(previous, current) == ["ui"]
