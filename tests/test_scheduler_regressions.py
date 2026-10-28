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


def test_due_job_is_retried_when_background_capacity_is_full(tmp_path, monkeypatch):
    monkeypatch.setattr(scheduler, 'RUNTIME_DIR', tmp_path)
    monkeypatch.setattr(scheduler, 'SCHEDULE_FILE', tmp_path / 'jobs.json')
    instance = scheduler.Scheduler()
    result = instance.create('test', scheduler._iso(scheduler._now() - timedelta(seconds=1)))
    monkeypatch.setattr('event_bus.emit_event', lambda *a, **k: {'success': True, 'launched': []})
    instance.tick()
    job = instance._jobs[result['job_id']]
    assert job['enabled']
    assert job['next_run'] is not None
    assert job['last_error'] == 'schedule_not_started'
    assert job['run_count'] == 0


def test_invalid_persisted_interval_cannot_hang_the_heartbeat(tmp_path, monkeypatch):
    monkeypatch.setattr(scheduler, 'RUNTIME_DIR', tmp_path)
    monkeypatch.setattr(scheduler, 'SCHEDULE_FILE', tmp_path / 'jobs.json')
    instance = scheduler.Scheduler()
    result = instance.create('test', scheduler._iso(scheduler._now() - timedelta(seconds=1)), 1)
    instance._jobs[result['job_id']]['interval_seconds'] = 0
    instance.tick()
    assert instance._jobs[result['job_id']]['last_error'] == 'invalid_interval'
    assert not instance._jobs[result['job_id']]['enabled']
