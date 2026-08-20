import task_runtime
from proactive_runtime import ProactiveRuntime


class FakeTaskRuntime:
    def __init__(self):
        self.calls = []

    def spawn(self, goal, **kwargs):
        self.calls.append((goal, kwargs))
        return {"success": True, "task_id": "task-1"}


def test_proactive_spawn_preserves_exact_parent_correlation_and_depth(monkeypatch):
    fake = FakeTaskRuntime()
    monkeypatch.setattr(task_runtime, "get_runtime", lambda: fake)
    runtime = ProactiveRuntime(dedupe_seconds=0, context_rules=[])
    event = {
        "id": "event-A",
        "type": "schedule.due",
        "payload": {"goal": "check context"},
        "correlation_id": "root-1",
        "causation_depth": 2,
    }

    result = runtime.handle(event)

    assert result["spawn"]["success"] is True
    assert fake.calls == [("check context", {
        "session_id": "proactive:root-1",
        "parent_event_id": "event-A",
        "correlation_id": "root-1",
        "causation_depth": 2,
    })]


def test_proactive_spawn_uses_event_id_as_root_correlation(monkeypatch):
    fake = FakeTaskRuntime()
    monkeypatch.setattr(task_runtime, "get_runtime", lambda: fake)
    runtime = ProactiveRuntime(dedupe_seconds=0, context_rules=[])
    runtime.handle({"id": "event-B", "type": "schedule.due", "payload": {"goal": "run task"}})

    _, kwargs = fake.calls[0]
    assert kwargs["parent_event_id"] == "event-B"
    assert kwargs["correlation_id"] == "event-B"
    assert kwargs["causation_depth"] == 0


def test_task_completion_emission_advances_depth_and_keeps_exact_parent(monkeypatch):
    emitted = []
    monkeypatch.setattr(task_runtime, "emit_event", lambda event_type, payload, **metadata: emitted.append((event_type, payload, metadata)), raising=False)
    import event_bus
    monkeypatch.setattr(event_bus, "emit_event", lambda event_type, payload, **metadata: emitted.append((event_type, payload, metadata)))

    task_runtime.TaskRuntime._emit(
        "task.completed",
        {"task_id": "task-1"},
        task={"parent_event_id": "event-A", "correlation_id": "root-1", "causation_depth": 2},
    )

    assert emitted == [("task.completed", {"task_id": "task-1"}, {
        "source": "task_runtime",
        "correlation_id": "root-1",
        "parent_event_id": "event-A",
        "causation_depth": 3,
    })]
