import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import event_bus
from event_bus import EventBus


def _paths(tmp_path, monkeypatch):
    monkeypatch.setattr(event_bus, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(event_bus, "TRIGGER_FILE", tmp_path / "triggers.json")
    monkeypatch.setattr(event_bus, "EVENT_LOG", tmp_path / "events.jsonl")
    return event_bus.TRIGGER_FILE


def _write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def test_load_skips_unhashable_trigger_id(tmp_path, monkeypatch):
    path = _paths(tmp_path, monkeypatch)
    _write(path, [{"id": ["bad"], "event_type": "x", "goal": "do"}])
    assert EventBus()._triggers == {}


def test_load_skips_empty_required_trigger_fields(tmp_path, monkeypatch):
    path = _paths(tmp_path, monkeypatch)
    _write(path, [
        {"id": " ", "event_type": "x", "goal": "do"},
        {"id": "a", "event_type": " ", "goal": "do"},
        {"id": "b", "event_type": "x", "goal": " "},
    ])
    assert EventBus()._triggers == {}


def test_load_normalizes_legacy_string_enabled_false(tmp_path, monkeypatch):
    path = _paths(tmp_path, monkeypatch)
    _write(path, [{"id": "a", "event_type": "x", "goal": "do", "enabled": "false"}])
    assert EventBus()._triggers["a"]["enabled"] is False


def test_load_normalizes_malformed_numeric_fields(tmp_path, monkeypatch):
    path = _paths(tmp_path, monkeypatch)
    _write(path, [{
        "id": "a", "event_type": "x", "goal": "do",
        "cooldown_seconds": "bogus", "fire_count": -4,
    }])
    trigger = EventBus()._triggers["a"]
    assert trigger["cooldown_seconds"] == 0
    assert trigger["fire_count"] == 0


def test_load_accepts_numeric_string_fields(tmp_path, monkeypatch):
    path = _paths(tmp_path, monkeypatch)
    _write(path, [{
        "id": "a", "event_type": "x", "goal": "do",
        "cooldown_seconds": "12", "fire_count": "3",
    }])
    trigger = EventBus()._triggers["a"]
    assert trigger["cooldown_seconds"] == 12
    assert trigger["fire_count"] == 3


def test_future_last_fired_timestamp_does_not_block_trigger(tmp_path, monkeypatch):
    _paths(tmp_path, monkeypatch)
    bus = EventBus()
    now = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(event_bus, "_now", lambda: now)
    future = (now + timedelta(hours=1)).isoformat()
    assert bus._cooldown_active({"cooldown_seconds": 60, "last_fired_at": future}) is False


def test_malformed_causation_depth_is_normalized_to_zero(tmp_path, monkeypatch):
    _paths(tmp_path, monkeypatch)
    bus = EventBus()
    monkeypatch.setattr("proactive_runtime.get_proactive_runtime", lambda: SimpleNamespace(handle=lambda event, goals: {"launched": [], "decision": {}}))
    result = bus.emit("x", causation_depth="bogus")
    assert result["event"]["causation_depth"] == 0


def test_non_dict_trigger_runtime_result_isolated_and_released(tmp_path, monkeypatch):
    _paths(tmp_path, monkeypatch)
    bus = EventBus()
    trigger_id = bus.create_trigger("x", "do")["trigger_id"]
    monkeypatch.setattr("proactive_runtime.get_proactive_runtime", lambda: SimpleNamespace(handle=lambda event, goals: None))
    result = bus.emit("x", correlation_id="corr")
    trigger = bus._triggers[trigger_id]
    assert result["success"] is False
    assert trigger["last_error"]
    assert trigger["recent_correlations"] == []
