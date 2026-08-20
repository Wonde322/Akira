import json

from proactive_action_control import ProactiveActionController
from proactive_action_lifecycle import ProactiveActionLifecycle


class FakeRuntime:
    def __init__(self, tasks=None, cancel_result=None):
        self.tasks = list(tasks or [])
        self.cancel_result = cancel_result or {"success": True, "status": "cancelled"}
        self.cancelled = []

    def list_tasks(self, limit=100): return {"success": True, "tasks": list(self.tasks)}
    def cancel(self, task_id): self.cancelled.append(str(task_id)); return dict(self.cancel_result, task_id=str(task_id))
    def status(self, task_id): return {"success": True, "task": {"id": str(task_id), "status": "running"}}


def test_lifecycle_persists_started_item(tmp_path):
    path = tmp_path / "lifecycle.json"
    lifecycle = ProactiveActionLifecycle(clock=lambda: "t1", path=path)
    lifecycle.started("task-1", "Проверить контекст", kind="inspect")
    assert path.exists()
    restored = ProactiveActionLifecycle(path=path)
    assert restored.get("task-1")["goal"] == "Проверить контекст"
    assert restored.get("task-1")["status"] == "running"


def test_lifecycle_persists_terminal_result(tmp_path):
    path = tmp_path / "lifecycle.json"
    lifecycle = ProactiveActionLifecycle(clock=lambda: "now", path=path)
    lifecycle.started("task-1", "Помочь")
    lifecycle.completed("task-1", "Готово")
    restored = ProactiveActionLifecycle(path=path)
    assert restored.get("task-1")["status"] == "completed"
    assert restored.get("task-1")["result"] == "Готово"


def test_reconcile_marks_completed(tmp_path):
    lifecycle = ProactiveActionLifecycle(path=tmp_path / "lifecycle.json")
    lifecycle.started("task-1", "Проверить")
    changed = lifecycle.reconcile([{"id": "task-1", "status": "completed", "result": "ok", "finished_at": "done"}])
    assert changed[0]["status"] == "completed"
    assert lifecycle.get("task-1")["result"] == "ok"


def test_reconcile_marks_failed(tmp_path):
    lifecycle = ProactiveActionLifecycle(path=tmp_path / "lifecycle.json")
    lifecycle.started("task-1", "Проверить")
    lifecycle.reconcile([{"id": "task-1", "status": "failed", "error": "boom"}])
    assert lifecycle.get("task-1")["status"] == "failed"
    assert lifecycle.get("task-1")["error"] == "boom"


def test_reconcile_marks_interrupted_after_restart(tmp_path):
    lifecycle = ProactiveActionLifecycle(path=tmp_path / "lifecycle.json")
    lifecycle.started("task-1", "Проверить")
    lifecycle.reconcile([{"id": "task-1", "status": "interrupted", "error": "restart"}])
    assert lifecycle.get("task-1")["status"] == "interrupted"


def test_reconcile_ignores_unknown_tasks(tmp_path):
    lifecycle = ProactiveActionLifecycle(path=tmp_path / "lifecycle.json")
    lifecycle.started("task-1", "Проверить")
    assert lifecycle.reconcile([{"id": "other", "status": "completed"}]) == []
    assert lifecycle.get("task-1")["status"] == "running"


def test_terminal_state_is_not_overwritten(tmp_path):
    lifecycle = ProactiveActionLifecycle(path=tmp_path / "lifecycle.json")
    lifecycle.started("task-1", "Проверить")
    lifecycle.completed("task-1", "done")
    lifecycle.reconcile([{"id": "task-1", "status": "failed", "error": "late"}])
    assert lifecycle.get("task-1")["status"] == "completed"


def test_active_excludes_terminal_items(tmp_path):
    lifecycle = ProactiveActionLifecycle(path=tmp_path / "lifecycle.json")
    lifecycle.started("active", "A"); lifecycle.started("done", "B"); lifecycle.completed("done")
    assert [item["task_id"] for item in lifecycle.active()] == ["active"]


def test_controller_recovers_all_persisted_states(tmp_path):
    lifecycle = ProactiveActionLifecycle(path=tmp_path / "lifecycle.json")
    lifecycle.started("done", "A"); lifecycle.started("broken", "B"); lifecycle.started("live", "C")
    runtime = FakeRuntime([{"id": "done", "status": "completed", "result": "ok"}, {"id": "broken", "status": "interrupted", "error": "restart"}, {"id": "live", "status": "running"}])
    changed = ProactiveActionController(runtime, lifecycle).recover()
    assert {item["task_id"] for item in changed} == {"done", "broken"}
    assert lifecycle.get("live")["status"] == "running"


def test_controller_cancel_updates_lifecycle(tmp_path):
    lifecycle = ProactiveActionLifecycle(path=tmp_path / "lifecycle.json")
    lifecycle.started("task-1", "Проверить")
    runtime = FakeRuntime()
    result = ProactiveActionController(runtime, lifecycle).cancel("task-1")
    assert result["success"] is True
    assert lifecycle.get("task-1")["status"] == "cancelled"
    assert runtime.cancelled == ["task-1"]


def test_controller_does_not_cancel_unknown_proactive_action(tmp_path):
    lifecycle = ProactiveActionLifecycle(path=tmp_path / "lifecycle.json")
    runtime = FakeRuntime()
    result = ProactiveActionController(runtime, lifecycle).cancel("missing")
    assert result["success"] is False
    assert result["error"] == "proactive_action_not_found"
    assert runtime.cancelled == []


def test_controller_status_contains_both_projections(tmp_path):
    lifecycle = ProactiveActionLifecycle(path=tmp_path / "lifecycle.json")
    lifecycle.started("task-1", "Проверить")
    result = ProactiveActionController(FakeRuntime(), lifecycle).status("task-1")
    assert result["lifecycle"]["task_id"] == "task-1"
    assert result["runtime"]["success"] is True
