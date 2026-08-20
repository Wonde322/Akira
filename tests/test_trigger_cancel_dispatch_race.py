import event_bus


def test_cancelled_trigger_is_skipped_before_its_dispatch(monkeypatch, tmp_path):
    monkeypatch.setattr(event_bus, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(event_bus, "TRIGGER_FILE", tmp_path / "triggers.json")
    monkeypatch.setattr(event_bus, "EVENT_LOG", tmp_path / "events.jsonl")
    bus = event_bus.EventBus()
    first = bus.create_trigger("demo.event", "first goal")["trigger_id"]
    second = bus.create_trigger("demo.event", "second goal")["trigger_id"]

    class Runtime:
        def __init__(self):
            self.calls = []
        def handle(self, event, goals):
            self.calls.append(event["trigger_id"])
            if event["trigger_id"] == first:
                bus.cancel_trigger(second)
            return {"decision": {"action": "spawn_task"}, "spawn": {"success": True, "task_id": "task-1"}, "launched": [{"task_id": "task-1"}]}

    import proactive_runtime
    runtime = Runtime()
    monkeypatch.setattr(proactive_runtime, "get_proactive_runtime", lambda: runtime)

    bus.emit("demo.event", {}, correlation_id="root")

    assert runtime.calls == [first]
    trigger = next(item for item in bus.list_triggers()["triggers"] if item["id"] == second)
    assert trigger["enabled"] is False
    assert trigger["recent_correlations"] == []
