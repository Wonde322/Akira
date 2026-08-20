import json

import task_runtime


def test_restart_emits_interrupted_event_for_previously_running_task(monkeypatch, tmp_path):
    task_file = tmp_path / "background_tasks.json"
    task_dir = tmp_path / "tasks"
    task_file.write_text(json.dumps([{
        "id": "task-1", "goal": "finish work", "session_id": "proactive:root",
        "parent_event_id": "event-1", "correlation_id": "root", "causation_depth": 2,
        "status": "running", "created_at": "2026-01-01T00:00:00",
        "started_at": "2026-01-01T00:00:01", "finished_at": None,
        "result": None, "error": None,
    }]), encoding="utf-8")
    monkeypatch.setattr(task_runtime, "TASK_FILE", task_file)
    monkeypatch.setattr(task_runtime, "TASK_DIR", task_dir)
    events = []
    monkeypatch.setattr(task_runtime.TaskRuntime, "_emit", staticmethod(lambda event_type, payload, task=None: events.append((event_type, payload, task))))

    runtime = task_runtime.TaskRuntime(max_workers=1)
    try:
        assert runtime.status("task-1")["task"]["status"] == "interrupted"
        assert len(events) == 1
        event_type, payload, task = events[0]
        assert event_type == "task.interrupted"
        assert payload["task_id"] == "task-1"
        assert task["correlation_id"] == "root"
        assert task["parent_event_id"] == "event-1"
        assert task["causation_depth"] == 2
    finally:
        runtime._executor.shutdown(wait=True)


def test_restart_does_not_emit_for_already_terminal_task(monkeypatch, tmp_path):
    task_file = tmp_path / "background_tasks.json"
    task_file.write_text(json.dumps([{
        "id": "task-1", "goal": "done", "session_id": "background:task-1",
        "status": "completed", "created_at": "2026-01-01T00:00:00",
        "started_at": "2026-01-01T00:00:01", "finished_at": "2026-01-01T00:00:02",
        "result": "ok", "error": None,
    }]), encoding="utf-8")
    monkeypatch.setattr(task_runtime, "TASK_FILE", task_file)
    monkeypatch.setattr(task_runtime, "TASK_DIR", tmp_path / "tasks")
    events = []
    monkeypatch.setattr(task_runtime.TaskRuntime, "_emit", staticmethod(lambda *args, **kwargs: events.append(args)))

    runtime = task_runtime.TaskRuntime(max_workers=1)
    try:
        assert runtime.status("task-1")["task"]["status"] == "completed"
        assert events == []
    finally:
        runtime._executor.shutdown(wait=True)
