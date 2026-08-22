import importlib
import json


def _runtime(monkeypatch, tmp_path):
    import task_runtime
    task_runtime = importlib.reload(task_runtime)
    monkeypatch.setattr(task_runtime, "TASK_DIR", tmp_path / "tasks")
    monkeypatch.setattr(task_runtime, "TASK_FILE", tmp_path / "background_tasks.json")
    return task_runtime


def test_loaded_active_task_becomes_interrupted(monkeypatch, tmp_path):
    module = _runtime(monkeypatch, tmp_path)
    module.TASK_FILE.parent.mkdir(parents=True)
    module.TASK_FILE.write_text(json.dumps([{"id": "t1", "goal": "work", "status": "running"}]), encoding="utf-8")
    runtime = module.TaskRuntime(max_workers=1)
    assert runtime.status("t1")["task"]["status"] == "interrupted"
    runtime.shutdown(wait=True)


def test_atomic_save_leaves_valid_json(monkeypatch, tmp_path):
    module = _runtime(monkeypatch, tmp_path)
    runtime = module.TaskRuntime(max_workers=1)
    with runtime._lock:
        runtime._tasks["t1"] = runtime._make_task("work")
        runtime._tasks["t1"]["id"] = "t1"
        runtime._save()
    assert json.loads(module.TASK_FILE.read_text(encoding="utf-8"))[0]["id"] == "t1"
    runtime.shutdown(wait=True)


def test_constructor_rejects_zero_workers(monkeypatch, tmp_path):
    module = _runtime(monkeypatch, tmp_path)
    try:
        module.TaskRuntime(max_workers=0)
    except ValueError:
        return
    raise AssertionError("zero workers must be rejected")
