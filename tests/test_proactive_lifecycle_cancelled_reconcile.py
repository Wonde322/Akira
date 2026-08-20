from proactive_action_lifecycle import ProactiveActionLifecycle


def test_reconcile_marks_running_action_cancelled(tmp_path):
    lifecycle = ProactiveActionLifecycle(path=tmp_path / "lifecycle.json", clock=lambda: "2026-08-20T15:40:00+04:00")
    lifecycle.started("task-1", "do something")

    changed = lifecycle.reconcile([{
        "id": "task-1",
        "status": "cancelled",
        "error": "Cancelled by user",
        "finished_at": "2026-08-20T15:41:00+04:00",
    }])

    assert len(changed) == 1
    assert changed[0]["status"] == "cancelled"
    assert changed[0]["error"] == "Cancelled by user"
    assert changed[0]["finished_at"] == "2026-08-20T15:41:00+04:00"
    assert lifecycle.active() == []


def test_reconcile_cancelled_uses_default_reason(tmp_path):
    lifecycle = ProactiveActionLifecycle(path=tmp_path / "lifecycle.json")
    lifecycle.started("task-1", "do something")

    lifecycle.reconcile([{"id": "task-1", "status": "cancelled"}])

    item = lifecycle.get("task-1")
    assert item["status"] == "cancelled"
    assert item["error"] == "Cancelled by user"
