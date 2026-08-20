from proactive_action_lifecycle import ProactiveActionLifecycle


def test_reconcile_marks_missing_running_task_interrupted(tmp_path):
    lifecycle = ProactiveActionLifecycle(clock=lambda: "2026-08-20T16:00:00+04:00", path=tmp_path / "lifecycle.json")
    lifecycle.started("task-1", "do something")

    changed = lifecycle.reconcile([])

    assert changed == [{
        "task_id": "task-1",
        "goal": "do something",
        "kind": None,
        "correlation_id": None,
        "status": "interrupted",
        "result": None,
        "error": "Task disappeared before lifecycle reconciliation.",
        "started_at": "2026-08-20T16:00:00+04:00",
        "finished_at": "2026-08-20T16:00:00+04:00",
    }]
    assert lifecycle.active() == []


def test_reconcile_keeps_existing_running_task_active(tmp_path):
    lifecycle = ProactiveActionLifecycle(clock=lambda: "now", path=tmp_path / "lifecycle.json")
    lifecycle.started("task-1", "do something")

    assert lifecycle.reconcile([{"id": "task-1", "status": "running"}]) == []
    assert lifecycle.get("task-1")["status"] == "running"
