from event_bus import EventBus


def test_malformed_persisted_fire_count_is_recovered(tmp_path, monkeypatch):
    import event_bus
    monkeypatch.setattr(event_bus, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(event_bus, "TRIGGER_FILE", tmp_path / "triggers.json")
    monkeypatch.setattr(event_bus, "EVENT_LOG", tmp_path / "events.jsonl")
    bus = EventBus()
    trigger = {"id": "t1", "fire_count": "bogus", "recent_correlations": []}
    bus._triggers["t1"] = trigger
    bus._record_results([(trigger, {"spawn": {"success": True, "task_id": "task-1"}})], "corr-1")
    assert bus._triggers["t1"]["fire_count"] == 1
