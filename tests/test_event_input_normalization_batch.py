import json
import sys
import types
from datetime import datetime

import event_bus
from event_bus import EventBus


def _bus(tmp_path, monkeypatch):
    monkeypatch.setattr(event_bus, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(event_bus, "TRIGGER_FILE", tmp_path / "triggers.json")
    monkeypatch.setattr(event_bus, "EVENT_LOG", tmp_path / "events.jsonl")
    return EventBus()


def _runtime(monkeypatch, result=None):
    calls = []

    class Runtime:
        def handle(self, event, goals):
            calls.append((event, goals))
            return result or {"launched": [], "decision": {"action": "ignore"}}

    module = types.SimpleNamespace(get_proactive_runtime=lambda: Runtime())
    monkeypatch.setitem(sys.modules, "proactive_runtime", module)
    return calls


def test_emit_rejects_empty_event_type(tmp_path, monkeypatch):
    bus = _bus(tmp_path, monkeypatch)
    result = bus.emit("   ")
    assert result["success"] is False
    assert result["error"] == "empty_event_type"
    assert not (tmp_path / "events.jsonl").exists()


def test_emit_strips_event_type(tmp_path, monkeypatch):
    bus = _bus(tmp_path, monkeypatch)
    calls = _runtime(monkeypatch)
    result = bus.emit("  task.completed  ")
    assert result["success"] is True
    assert calls[0][0]["type"] == "task.completed"


def test_emit_normalizes_non_json_payload_values(tmp_path, monkeypatch):
    bus = _bus(tmp_path, monkeypatch)
    calls = _runtime(monkeypatch)
    result = bus.emit("signal", {"when": datetime(2026, 8, 20, 17, 0), "values": {1, 2}})
    assert result["success"] is True
    payload = calls[0][0]["payload"]
    assert payload["when"] == "2026-08-20 17:00:00"
    assert isinstance(payload["values"], str)
    logged = json.loads((tmp_path / "events.jsonl").read_text().strip())
    assert logged["payload"] == payload


def test_emit_recovers_from_circular_payload(tmp_path, monkeypatch):
    bus = _bus(tmp_path, monkeypatch)
    calls = _runtime(monkeypatch)
    payload = {}
    payload["self"] = payload
    result = bus.emit("signal", payload)
    assert result["success"] is True
    assert calls[0][0]["payload"] == {}


def test_emit_ignores_non_dict_payload(tmp_path, monkeypatch):
    bus = _bus(tmp_path, monkeypatch)
    calls = _runtime(monkeypatch)
    bus.emit("signal", ["not", "a", "dict"])
    assert calls[0][0]["payload"] == {}


def test_emit_normalizes_metadata_and_correlation_fallback(tmp_path, monkeypatch):
    bus = _bus(tmp_path, monkeypatch)
    calls = _runtime(monkeypatch)
    bus.emit("signal", {}, parent_event_id="  parent-1  ", correlation_id="  ", source="  user  ")
    event = calls[0][0]
    assert event["parent_event_id"] == "parent-1"
    assert event["correlation_id"] == "parent-1"
    assert event["source"] == "user"


def test_emit_falls_back_to_generated_correlation_and_default_source(tmp_path, monkeypatch):
    bus = _bus(tmp_path, monkeypatch)
    calls = _runtime(monkeypatch)
    bus.emit("signal", {}, correlation_id="   ", source="   ")
    event = calls[0][0]
    assert event["correlation_id"] == event["id"]
    assert event["source"] == "system"


def test_render_goal_handles_normalized_payload(tmp_path, monkeypatch):
    bus = _bus(tmp_path, monkeypatch)
    calls = _runtime(monkeypatch)
    trigger = bus.create_trigger("signal", "payload={{event.payload}}")
    result = bus.emit("signal", {"when": datetime(2026, 8, 20, 17, 0)})
    assert result["success"] is True
    assert calls[0][1] == ['payload={"when": "2026-08-20 17:00:00"}']
    assert trigger["success"] is True
