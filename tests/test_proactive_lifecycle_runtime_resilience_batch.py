import json

from proactive_action_control import ProactiveActionController
from proactive_action_lifecycle import ProactiveActionLifecycle


class Runtime:
    def __init__(self, *, listed=None, cancel=None, status=None, error=None):
        self.listed = listed
        self.cancel_result = cancel
        self.status_result = status
        self.error = error

    def list_tasks(self, limit=100):
        if self.error == "list": raise RuntimeError("list down")
        return self.listed

    def cancel(self, task_id):
        if self.error == "cancel": raise RuntimeError("cancel down")
        return self.cancel_result

    def status(self, task_id):
        if self.error == "status": raise RuntimeError("status down")
        return self.status_result


def test_load_skips_non_mapping_and_blank_identity_records(tmp_path):
    path = tmp_path / "lifecycle.json"
    path.write_text(json.dumps([None, [], {"task_id": " ", "goal": "x"}, {"task_id": "ok", "goal": "goal"}]), encoding="utf-8")
    lifecycle = ProactiveActionLifecycle(path=path)
    assert lifecycle.recent() == [lifecycle.get("ok")]


def test_load_normalizes_status_and_duplicate_identity(tmp_path):
    path = tmp_path / "lifecycle.json"
    path.write_text(json.dumps([{"task_id": "x", "goal": "one", "status": "BOGUS"}, {"task_id": " x ", "goal": "two", "status": " COMPLETED "}]), encoding="utf-8")
    lifecycle = ProactiveActionLifecycle(path=path)
    assert lifecycle.get("x")["status"] == "completed"
    assert lifecycle.get("x")["goal"] == "two"


def test_started_rejects_blank_task_id(tmp_path):
    lifecycle = ProactiveActionLifecycle(path=tmp_path / "lifecycle.json")
    assert lifecycle.started(" ", "goal") is None
    assert lifecycle.recent() == []


def test_reconcile_normalizes_terminal_status_case_and_result(tmp_path):
    lifecycle = ProactiveActionLifecycle(path=tmp_path / "lifecycle.json")
    lifecycle.started("x", "goal")
    changed = lifecycle.reconcile([{"id": " x ", "status": " COMPLETED ", "result": 42}])
    assert changed[0]["status"] == "completed"
    assert lifecycle.get("x")["result"] == "42"


def test_recover_ignores_runtime_exception(tmp_path):
    lifecycle = ProactiveActionLifecycle(path=tmp_path / "lifecycle.json")
    lifecycle.started("x", "goal")
    assert ProactiveActionController(Runtime(error="list"), lifecycle).recover() == []
    assert lifecycle.get("x")["status"] == "running"


def test_recover_ignores_malformed_runtime_response(tmp_path):
    lifecycle = ProactiveActionLifecycle(path=tmp_path / "lifecycle.json")
    lifecycle.started("x", "goal")
    assert ProactiveActionController(Runtime(listed=[]), lifecycle).recover() == []
    assert lifecycle.get("x")["status"] == "running"


def test_cancel_runtime_failure_does_not_change_lifecycle(tmp_path):
    lifecycle = ProactiveActionLifecycle(path=tmp_path / "lifecycle.json")
    lifecycle.started("x", "goal")
    result = ProactiveActionController(Runtime(error="cancel"), lifecycle).cancel("x")
    assert result["success"] is False
    assert lifecycle.get("x")["status"] == "running"


def test_status_runtime_failure_is_projected_safely(tmp_path):
    lifecycle = ProactiveActionLifecycle(path=tmp_path / "lifecycle.json")
    lifecycle.started("x", "goal")
    result = ProactiveActionController(Runtime(error="status"), lifecycle).status("x")
    assert result["success"] is False
    assert result["lifecycle"]["task_id"] == "x"
    assert result["runtime"]["success"] is False
