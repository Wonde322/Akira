from task_runtime import TaskRuntime
import event_bus


def test_proactive_task_keeps_root_correlation():
    runtime = object.__new__(TaskRuntime)
    task = runtime._make_task("check something", "proactive:event-123")

    assert task["session_id"] == "proactive:event-123"
    assert task["correlation_id"] == "event-123"


def test_regular_background_task_has_no_synthetic_correlation():
    runtime = object.__new__(TaskRuntime)
    task = runtime._make_task("check something", "background:task-123")

    assert task["correlation_id"] is None


def test_task_completion_emits_provenance(monkeypatch):
    captured = {}

    def fake_emit(event_type, payload, **metadata):
        captured["event_type"] = event_type
        captured["payload"] = payload
        captured["metadata"] = metadata
        return {"success": True}

    monkeypatch.setattr(event_bus, "emit_event", fake_emit)

    TaskRuntime._emit(
        "task.completed",
        {"task_id": "task-1"},
        task={"correlation_id": "event-123"},
    )

    assert captured["event_type"] == "task.completed"
    assert captured["metadata"] == {
        "source": "task_runtime",
        "parent_event_id": "event-123",
        "correlation_id": "event-123",
        "causation_depth": 1,
    }


def test_regular_task_completion_does_not_invent_parent(monkeypatch):
    captured = {}

    def fake_emit(event_type, payload, **metadata):
        captured["metadata"] = metadata
        return {"success": True}

    monkeypatch.setattr(event_bus, "emit_event", fake_emit)
    TaskRuntime._emit("task.completed", {"task_id": "task-1"}, task={})

    assert captured["metadata"] == {"source": "task_runtime"}
