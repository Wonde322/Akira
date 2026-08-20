from datetime import datetime, timedelta

from task_watchdog import TaskWatchdog


class FakeRuntime:
    def __init__(self, tasks):
        self.tasks = tasks

    def list_tasks(self, limit=50):
        return {"success": True, "tasks": list(self.tasks)}


def test_watchdog_reports_stalled_task_once():
    now = datetime(2026, 8, 20, 12, 0, 0)
    events = []
    runtime = FakeRuntime([{
        "id": "slow-1", "goal": "long job", "session_id": "background:slow-1",
        "status": "running", "started_at": (now - timedelta(seconds=601)).isoformat(),
    }])
    watchdog = TaskWatchdog(runtime=runtime, stall_seconds=600, now=lambda: now,
                            emit=lambda *args, **kwargs: events.append((args, kwargs)) or {"success": True})
    first = watchdog.scan()
    second = watchdog.scan()
    assert first["stalled"] == ["slow-1"]
    assert second["stalled"] == []
    assert len(events) == 1
    assert events[0][0][0] == "task.failed"
    assert events[0][0][1]["watchdog_kind"] == "stalled"


def test_watchdog_reports_interrupted_task_once():
    events = []
    runtime = FakeRuntime([{
        "id": "old-1", "goal": "old job", "session_id": "background:old-1",
        "status": "interrupted", "error": "restart",
    }])
    watchdog = TaskWatchdog(runtime=runtime,
                            emit=lambda *args, **kwargs: events.append((args, kwargs)) or {"success": True})
    assert watchdog.scan()["interrupted"] == ["old-1"]
    assert watchdog.scan()["interrupted"] == []
    assert events[0][0][1]["watchdog_kind"] == "interrupted"


def test_watchdog_ignores_fresh_and_completed_tasks():
    now = datetime(2026, 8, 20, 12, 0, 0)
    events = []
    runtime = FakeRuntime([
        {"id": "fresh", "status": "running", "started_at": now.isoformat()},
        {"id": "done", "status": "completed", "started_at": (now - timedelta(days=1)).isoformat()},
    ])
    watchdog = TaskWatchdog(runtime=runtime, now=lambda: now,
                            emit=lambda *args, **kwargs: events.append((args, kwargs)))
    result = watchdog.scan()
    assert result["stalled"] == []
    assert result["interrupted"] == []
    assert events == []


def test_watchdog_skips_tasks_with_invalid_start_time():
    runtime = FakeRuntime([{"id": "bad", "status": "running", "started_at": "not-a-date"}])
    watchdog = TaskWatchdog(runtime=runtime, emit=lambda *args, **kwargs: {"success": True})
    assert watchdog.scan()["stalled"] == []
