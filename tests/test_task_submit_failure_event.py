import task_runtime
from task_runtime import TaskRuntime


class RejectingExecutor:
    def submit(self, *_args):
        raise RuntimeError("executor unavailable")


def test_submit_failure_emits_task_failed_with_provenance(tmp_path, monkeypatch):
    monkeypatch.setattr(task_runtime, "TASK_DIR", tmp_path / "tasks")
    monkeypatch.setattr(task_runtime, "TASK_FILE", tmp_path / "tasks.json")
    events = []
    monkeypatch.setattr("event_bus.emit_event", lambda event_type, payload, **metadata: events.append((event_type, payload, metadata)))

    runtime = TaskRuntime(max_workers=1)
    runtime._executor.shutdown(wait=False)
    runtime._executor = RejectingExecutor()

    result = runtime.spawn(
        "сломанная задача",
        parent_event_id="event-1",
        correlation_id="root-1",
        causation_depth=2,
    )

    assert result["success"] is False
    assert result["status"] == "failed"
    task = runtime.status(result["task_id"])["task"]
    assert task["status"] == "failed"
    assert task["started_at"] is None
    assert task["finished_at"] is not None
    assert events == [(
        "task.failed",
        {
            "task_id": result["task_id"],
            "goal": "сломанная задача",
            "error": "executor unavailable",
            "session_id": f"background:{result['task_id']}",
        },
        {
            "source": "task_runtime",
            "correlation_id": "root-1",
            "parent_event_id": "event-1",
            "causation_depth": 3,
        },
    )]
