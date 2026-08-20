from proactive_runtime import ProactiveAction, ProactiveRuntime, MAX_COMPLETION_RESULT_CHARS


class EmptyStore:
    def active(self):
        return []

    def list(self):
        return []


class EmptyPolicy:
    def decide(self, *_args, **_kwargs):
        return None


class EmptyProposer:
    def propose(self, *_args, **_kwargs):
        return []


def make_runtime():
    return ProactiveRuntime(
        dedupe_seconds=0,
        context_rule_store=EmptyStore(),
        reasoning_policy=EmptyPolicy(),
        action_proposer=EmptyProposer(),
    )


def test_proactive_completed_task_delivers_result():
    runtime = make_runtime()
    decision = runtime.decide({
        "id": "event-1",
        "type": "task.completed",
        "payload": {
            "goal": "Проверить текущий контекст",
            "result": "Нашёл активное окно и подготовил следующий шаг.",
            "session_id": "proactive:event-0",
        },
    })

    assert decision.action == ProactiveAction.NOTIFY
    assert decision.reason == "proactive_task_completed"
    assert "Нашёл активное окно" in decision.notification


def test_completion_without_result_keeps_compact_message():
    runtime = make_runtime()
    decision = runtime.decide({
        "id": "event-2",
        "type": "task.completed",
        "payload": {
            "goal": "Проверить задачу",
            "session_id": "proactive:event-1",
        },
    })

    assert decision.notification == "Задача завершена: Проверить задачу"


def test_long_proactive_result_is_bounded():
    message = ProactiveRuntime._message_for_completion({
        "goal": "Длинная задача",
        "result": "x" * (MAX_COMPLETION_RESULT_CHARS + 100),
    })

    assert message.endswith("…")
    assert len(message.split("\n\n", 1)[1]) == MAX_COMPLETION_RESULT_CHARS + 1
