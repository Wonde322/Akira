from datetime import timedelta

import scheduler


def test_scheduler_due_payload_uses_actual_launch_time(monkeypatch, tmp_path):
    monkeypatch.setattr(scheduler, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(scheduler, "SCHEDULE_FILE", tmp_path / "scheduled_jobs.json")
    instance = scheduler.Scheduler()
    created = instance.create("test", scheduler._iso(scheduler._now() - timedelta(seconds=1)))
    captured = {}

    def fake_emit(event_type, payload, source=None):
        captured.update(payload)
        return {"success": True, "launched": []}

    monkeypatch.setattr("event_bus.emit_event", fake_emit)
    instance.tick()
    assert captured["scheduled_for"] is not None


def test_scheduler_rejects_boolean_interval(tmp_path, monkeypatch):
    monkeypatch.setattr(scheduler, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(scheduler, "SCHEDULE_FILE", tmp_path / "scheduled_jobs.json")
    instance = scheduler.Scheduler()
    result = instance.create("test", scheduler._iso(scheduler._now()), True)
    assert result["error"] == "invalid_interval"
