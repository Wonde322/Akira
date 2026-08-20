from event_bus import EventBus


def test_malformed_persisted_cooldown_does_not_break_dispatch(tmp_path, monkeypatch):
    import event_bus
    monkeypatch.setattr(event_bus, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(event_bus, "TRIGGER_FILE", tmp_path / "triggers.json")
    monkeypatch.setattr(event_bus, "EVENT_LOG", tmp_path / "events.jsonl")
    bus = EventBus()
    assert bus._cooldown_active({"cooldown_seconds": "bogus", "last_fired_at": "2026-08-20T16:00:00+04:00"}) is False
