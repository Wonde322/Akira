from proactive_action_handlers import ProactiveActionHandlers
from proactive_action_lifecycle import ProactiveActionLifecycle
from proactive_runtime import ProactiveRuntime


class EmptyStore:
    def active(self): return []
    def list(self): return []


class EmptyPolicy:
    def decide(self, *_args, **_kwargs): return None


class EmptyProposer:
    def propose(self, *_args, **_kwargs): return []


def test_user_selected_action_starts_lifecycle():
    lifecycle = ProactiveActionLifecycle(clock=lambda: "t1")
    handlers = ProactiveActionHandlers(
        lambda goal, session_id: {"success": True, "task_id": "task-1"}, lifecycle=lifecycle,
    )
    result = handlers.handle({"id": "event-1", "type": "proactive.help_requested", "payload": {"goal": "Разобраться"}})
    assert result["success"] is True
    assert result["lifecycle"]["status"] == "running"
    assert lifecycle.get("task-1")["goal"] == "Разобраться"


def test_proactive_completion_finishes_lifecycle():
    lifecycle = ProactiveActionLifecycle(clock=lambda: "now")
    lifecycle.started("task-1", "Проверить контекст")
    runtime = ProactiveRuntime(dedupe_seconds=0, context_rule_store=EmptyStore(), reasoning_policy=EmptyPolicy(), action_proposer=EmptyProposer(), lifecycle=lifecycle)
    result = runtime.handle({"id": "event-2", "type": "task.completed", "payload": {"task_id": "task-1", "goal": "Проверить контекст", "result": "Готово", "session_id": "proactive:event-1"}})
    assert result["lifecycle"]["status"] == "completed"
    assert lifecycle.get("task-1")["result"] == "Готово"


def test_proactive_failure_finishes_lifecycle():
    lifecycle = ProactiveActionLifecycle(clock=lambda: "now")
    lifecycle.started("task-2", "Проверить контекст")
    runtime = ProactiveRuntime(dedupe_seconds=0, context_rule_store=EmptyStore(), reasoning_policy=EmptyPolicy(), action_proposer=EmptyProposer(), lifecycle=lifecycle)
    result = runtime.handle({"id": "event-3", "type": "task.failed", "payload": {"task_id": "task-2", "goal": "Проверить контекст", "error": "boom", "session_id": "proactive:event-1"}})
    assert result["lifecycle"]["status"] == "failed"
    assert lifecycle.get("task-2")["error"] == "boom"


def test_non_proactive_task_does_not_enter_lifecycle():
    lifecycle = ProactiveActionLifecycle()
    runtime = ProactiveRuntime(dedupe_seconds=0, context_rule_store=EmptyStore(), reasoning_policy=EmptyPolicy(), action_proposer=EmptyProposer(), lifecycle=lifecycle)
    result = runtime.handle({"id": "event-4", "type": "task.completed", "payload": {"task_id": "task-x", "session_id": "background:x"}})
    assert result["lifecycle"] is None
    assert lifecycle.get("task-x") is None
