import sys
import types

import event_bus
from event_bus import EventBus


def _bus(tmp_path, monkeypatch):
    monkeypatch.setattr(event_bus, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(event_bus, "TRIGGER_FILE", tmp_path / "triggers.json")
    monkeypatch.setattr(event_bus, "EVENT_LOG", tmp_path / "events.jsonl")
    return EventBus()


def _runtime(monkeypatch, result):
    class Runtime:
        def handle(self, event, goals):
            return result
    monkeypatch.setitem(sys.modules, "proactive_runtime", types.SimpleNamespace(get_proactive_runtime=lambda: Runtime()))


def test_trigger_ignores_non_mapping_spawn(tmp_path, monkeypatch):
    bus = _bus(tmp_path, monkeypatch); _runtime(monkeypatch, {"spawn": "bad", "decision": {"action": "spawn_task"}})
    tid = bus.create_trigger("signal", "go")["trigger_id"]
    result = bus.emit("signal")
    assert result["success"] is True
    assert bus._triggers[tid]["last_error"] == "spawn_failed"


def test_trigger_ignores_non_mapping_decision(tmp_path, monkeypatch):
    bus = _bus(tmp_path, monkeypatch); _runtime(monkeypatch, {"spawn": {}, "decision": ["spawn_task"]})
    tid = bus.create_trigger("signal", "go")["trigger_id"]
    assert bus.emit("signal")["success"] is True
    assert bus._triggers[tid]["recent_correlations"] == []


def test_successful_spawn_still_records_task_id(tmp_path, monkeypatch):
    bus = _bus(tmp_path, monkeypatch); _runtime(monkeypatch, {"spawn": {"success": True, "task_id": "t1"}, "decision": None})
    tid = bus.create_trigger("signal", "go")["trigger_id"]
    bus.emit("signal")
    assert bus._triggers[tid]["last_task_id"] == "t1"
    assert bus._triggers[tid]["fire_count"] == 1


def test_non_list_launched_string_is_not_split(tmp_path, monkeypatch):
    bus = _bus(tmp_path, monkeypatch); _runtime(monkeypatch, {"launched": "abc", "decision": {"action": "ignore"}})
    assert bus.emit("signal")["launched"] == []


def test_non_list_launched_mapping_is_not_iterated(tmp_path, monkeypatch):
    bus = _bus(tmp_path, monkeypatch); _runtime(monkeypatch, {"launched": {"task": 1}, "decision": {"action": "ignore"}})
    assert bus.emit("signal")["launched"] == []


def test_list_launched_is_preserved(tmp_path, monkeypatch):
    bus = _bus(tmp_path, monkeypatch); _runtime(monkeypatch, {"launched": [{"task_id": "a"}, {"task_id": "b"}], "decision": {}})
    assert bus.emit("signal")["launched"] == [{"task_id": "a"}, {"task_id": "b"}]


def test_malformed_result_with_trigger_releases_reservation(tmp_path, monkeypatch):
    bus = _bus(tmp_path, monkeypatch); _runtime(monkeypatch, None)
    tid = bus.create_trigger("signal", "go")["trigger_id"]
    result = bus.emit("signal", correlation_id="same")
    assert result["success"] is False
    assert bus._triggers[tid]["recent_correlations"] == []


def test_malformed_result_without_trigger_is_reported(tmp_path, monkeypatch):
    bus = _bus(tmp_path, monkeypatch); _runtime(monkeypatch, ["bad"])
    result = bus.emit("signal")
    assert result["success"] is False
    assert result["error"] == "proactive_runtime_error"
