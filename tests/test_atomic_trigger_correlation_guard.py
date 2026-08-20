import sys
import types


def _isolated_bus(monkeypatch, tmp_path):
    import event_bus
    monkeypatch.setattr(event_bus, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(event_bus, "EVENT_LOG", tmp_path / "events.jsonl")
    monkeypatch.setattr(event_bus, "TRIGGER_FILE", tmp_path / "triggers.json")
    return event_bus.EventBus()


def test_trigger_correlation_is_reserved_before_reentrant_dispatch(monkeypatch, tmp_path):
    bus = _isolated_bus(monkeypatch, tmp_path)
    trigger_id = bus.create_trigger("loop", "do work")["trigger_id"]
    calls = []

    class Runtime:
        def handle(self, event, goals):
            if goals:
                calls.append(event.get("trigger_id"))
                bus.emit("loop", {"nested": True}, correlation_id=event["correlation_id"])
                return {"spawn": {"success": True, "task_id": "task-1"}, "launched": [], "decision": {"action": "spawn_task"}}
            return {"launched": [], "decision": {"action": "ignore"}}

    monkeypatch.setitem(sys.modules, "proactive_runtime", types.SimpleNamespace(get_proactive_runtime=lambda: Runtime()))
    result = bus.emit("loop", {}, correlation_id="root")

    assert result["success"] is True
    assert calls == [trigger_id]
    assert bus.list_triggers()["triggers"][0]["fire_count"] == 1


def test_correlation_reservation_is_released_when_trigger_does_not_spawn(monkeypatch, tmp_path):
    bus = _isolated_bus(monkeypatch, tmp_path)
    trigger_id = bus.create_trigger("tick", "maybe work")["trigger_id"]
    calls = []

    class Runtime:
        def handle(self, event, goals):
            if goals:
                calls.append(event.get("trigger_id"))
            return {"spawn": {"success": False}, "launched": [], "decision": {"action": "ignore"}}

    monkeypatch.setitem(sys.modules, "proactive_runtime", types.SimpleNamespace(get_proactive_runtime=lambda: Runtime()))
    bus.emit("tick", {}, correlation_id="root")
    bus.emit("tick", {}, correlation_id="root")

    assert calls == [trigger_id, trigger_id]
