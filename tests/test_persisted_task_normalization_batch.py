import json

import task_runtime


def _runtime(tmp_path, monkeypatch, payload):
    task_file = tmp_path / "background_tasks.json"
    task_file.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(task_runtime, "TASK_DIR", tmp_path / "tasks")
    monkeypatch.setattr(task_runtime, "TASK_FILE", task_file)
    runtime = task_runtime.TaskRuntime(max_workers=1)
    return runtime, task_file


def test_skips_non_mapping_and_blank_identity(tmp_path, monkeypatch):
    runtime, _ = _runtime(tmp_path, monkeypatch, [None, [], {"id": " "}, {"id": "x", "goal": ""}])
    assert runtime.list_tasks()["tasks"] == []
    runtime._executor.shutdown(wait=True)


def test_trims_id_goal_and_session_id(tmp_path, monkeypatch):
    runtime, _ = _runtime(tmp_path, monkeypatch, [{"id": "  x  ", "goal": "  do it  ", "session_id": "  s  ", "status": "completed"}])
    task = runtime.status("x")["task"]
    assert (task["id"], task["goal"], task["session_id"]) == ("x", "do it", "s")
    runtime._executor.shutdown(wait=True)


def test_missing_session_id_gets_safe_default(tmp_path, monkeypatch):
    runtime, _ = _runtime(tmp_path, monkeypatch, [{"id": "x", "goal": "work", "status": "completed"}])
    assert runtime.status("x")["task"]["session_id"] == "background:x"
    runtime._executor.shutdown(wait=True)


def test_unknown_status_becomes_failed(tmp_path, monkeypatch):
    runtime, _ = _runtime(tmp_path, monkeypatch, [{"id": "x", "goal": "work", "status": "wat"}])
    assert runtime.status("x")["task"]["status"] == "failed"
    runtime._executor.shutdown(wait=True)


def test_status_is_case_and_space_normalized(tmp_path, monkeypatch):
    runtime, _ = _runtime(tmp_path, monkeypatch, [{"id": "x", "goal": "work", "status": " COMPLETED "}])
    assert runtime.status("x")["task"]["status"] == "completed"
    runtime._executor.shutdown(wait=True)


def test_bad_and_negative_causation_depth_become_zero(tmp_path, monkeypatch):
    runtime, _ = _runtime(tmp_path, monkeypatch, [
        {"id": "x", "goal": "one", "status": "completed", "causation_depth": "bad"},
        {"id": "y", "goal": "two", "status": "completed", "causation_depth": -3},
    ])
    assert runtime.status("x")["task"]["causation_depth"] == 0
    assert runtime.status("y")["task"]["causation_depth"] == 0
    runtime._executor.shutdown(wait=True)


def test_blank_provenance_ids_become_none(tmp_path, monkeypatch):
    runtime, _ = _runtime(tmp_path, monkeypatch, [{"id": "x", "goal": "work", "status": "completed", "parent_event_id": " ", "correlation_id": " c "}])
    task = runtime.status("x")["task"]
    assert task["parent_event_id"] is None
    assert task["correlation_id"] == "c"
    runtime._executor.shutdown(wait=True)


def test_normalized_payload_is_persisted_and_running_still_interrupts(tmp_path, monkeypatch):
    runtime, task_file = _runtime(tmp_path, monkeypatch, [{"id": " x ", "goal": " work ", "status": "RUNNING", "causation_depth": "2"}])
    task = runtime.status("x")["task"]
    saved = json.loads(task_file.read_text(encoding="utf-8"))
    assert task["status"] == "interrupted"
    assert saved == [task]
    runtime._executor.shutdown(wait=True)
