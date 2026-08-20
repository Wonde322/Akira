from task_runtime import TaskRuntime


class ImmediateExecutor:
    def submit(self, fn, *args):
        fn(*args)
        return object()


def test_immediate_completion_does_not_leave_stale_future(tmp_path, monkeypatch):
    monkeypatch.setattr("task_runtime.TASK_DIR", tmp_path / "tasks")
    monkeypatch.setattr("task_runtime.TASK_FILE", tmp_path / "tasks.json")
    runtime = TaskRuntime(max_workers=1)
    runtime._executor.shutdown(wait=False)
    runtime._executor = ImmediateExecutor()

    def finish_immediately(task_id):
        runtime._tasks[task_id]["status"] = "completed"
        runtime._tasks[task_id]["result"] = "done"

    runtime._run = finish_immediately
    result = runtime.spawn("быстрая задача")

    assert result["success"] is True
    assert result["status"] == "completed"
    assert result["task_id"] not in runtime._futures
