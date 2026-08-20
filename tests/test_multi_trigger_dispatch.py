import event_bus


class FakeRuntime:
    def __init__(self):
        self.calls = []
    def handle(self, event, goals):
        self.calls.append((event, goals))
        return {"success": True, "decision": {"action": "spawn_task"}, "spawn": {"success": True, "task_id": "task-" + str(len(self.calls))}, "launched": [{"task_id": "task-" + str(len(self.calls))}]}


def test_all_matching_triggers_are_dispatched(monkeypatch, tmp_path):
    monkeypatch.setattr(event_bus, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(event_bus, "TRIGGER_FILE", tmp_path / "triggers.json")
    monkeypatch.setattr(event_bus, "EVENT_LOG", tmp_path / "events.jsonl")
    runtime = FakeRuntime()
    monkeypatch.setattr(event_bus, "get_proactive_runtime", lambda: runtime, raising=False)
    bus = event_bus.EventBus()
    first = bus.create_trigger("demo.event", "first goal")["trigger_id"]
    second = bus.create_trigger("demo.event", "second goal")["trigger_id"]

    import proactive_runtime
    monkeypatch.setattr(proactive_runtime, "get_proactive_runtime", lambda: runtime)
    result = bus.emit("demo.event", {"value": 1})

    assert [goals[0] for _, goals in runtime.calls] == ["first goal", "second goal"]
    assert len(result["launched"]) == 2
    triggers = {item["id"]: item for item in bus.list_triggers()["triggers"]}
    assert triggers[first]["last_task_id"] == "task-1"
    assert triggers[second]["last_task_id"] == "task-2"


def test_trigger_and_non_trigger_event_still_have_single_runtime_pass(monkeypatch, tmp_path):
    monkeypatch.setattr(event_bus, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(event_bus, "TRIGGER_FILE", tmp_path / "triggers.json")
    monkeypatch.setattr(event_bus, "EVENT_LOG", tmp_path / "events.jsonl")
    runtime = FakeRuntime()
    import proactive_runtime
    monkeypatch.setattr(proactive_runtime, "get_proactive_runtime", lambda: runtime)
    bus = event_bus.EventBus()

    bus.emit("plain.event", {})
    assert len(runtime.calls) == 1
    assert runtime.calls[0][1] == []
