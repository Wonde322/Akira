import task_runtime


def test_terminal_event_sees_future_already_cleaned(tmp_path, monkeypatch):
    monkeypatch.setattr(task_runtime, "TASK_DIR", tmp_path / "tasks")
    monkeypatch.setattr(task_runtime, "TASK_FILE", tmp_path / "tasks.json")
    monkeypatch.setattr("brain.ask", lambda *_args, **_kwargs: "done")

    runtime = task_runtime.TaskRuntime(max_workers=1)
    seen = []

    def emit(event_type, _payload, task=None):
        seen.append((event_type, task_runtime.TaskRuntime.status(runtime, task["id"]), task["id"] in runtime._futures))

    monkeypatch.setattr(runtime, "_emit", emit)
    result = runtime.spawn("быстрая задача")
    runtime._executor.shutdown(wait=True)

    assert result["success"] is True
    assert seen and seen[0][0] == "task.completed"
    assert seen[0][1]["task"]["status"] == "completed"
    assert seen[0][2] is False
