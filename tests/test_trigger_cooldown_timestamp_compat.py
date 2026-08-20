from datetime import datetime

from event_bus import EventBus


def test_legacy_naive_cooldown_timestamp_does_not_crash(tmp_path, monkeypatch):
    import event_bus
    monkeypatch.setattr(event_bus, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(event_bus, "EVENT_LOG", tmp_path / "events.jsonl")
    monkeypatch.setattr(event_bus, "TRIGGER_FILE", tmp_path / "triggers.json")
    bus = EventBus()
    created = bus.create_trigger("demo.event", "check", cooldown_seconds=60)
    trigger = bus._triggers[created["trigger_id"]]
    trigger["last_fired_at"] = datetime.now().isoformat(timespec="seconds")
    assert bus._cooldown_active(trigger) is True
