from proactive_action_proposals import ProactiveActionProposer
from proactive_inbox import ProactiveInbox
from proactive_policy import PolicyRecommendation
from proactive_runtime import ProactiveAction, ProactiveRuntime


def test_repeated_context_gets_concrete_safe_choices():
    recommendation = PolicyRecommendation("ask_user", "repeated_task_context", goal="Проверить макет")
    proposals = ProactiveActionProposer.propose("desktop.context.repeated", {}, recommendation)
    assert [item["id"] for item in proposals] == ["help", "inspect", "continue"]
    assert all(item["kind"] in {"ask", "observe", "dismiss"} for item in proposals)


def test_long_dwell_gets_contextual_choices():
    recommendation = PolicyRecommendation("ask_user", "long_task_dwell", goal="Собрать презентацию")
    proposals = ProactiveActionProposer.propose("desktop.context.dwell", {}, recommendation)
    assert [item["id"] for item in proposals] == ["inspect", "help", "continue"]


def test_runtime_attaches_proposals_to_high_signal_question(tmp_path):
    inbox = ProactiveInbox(tmp_path / "inbox.json")
    runtime = ProactiveRuntime(inbox=inbox, dedupe_seconds=0)
    event = {"id": "evt-1", "type": "desktop.context.repeated", "payload": {"count": 3, "active_task": {"goal": "Проверить макет", "confidence": 0.9}}}
    result = runtime.handle(event)
    assert result["decision"]["action"] == ProactiveAction.ASK_USER.value
    assert result["attention"]["proposals"]
    assert result["attention"]["proposals"][0]["id"] == "help"


def test_inbox_preserves_proposals(tmp_path):
    inbox = ProactiveInbox(tmp_path / "inbox.json")
    item = inbox.push("Нужна помощь?", action="ask_user", proposals=[{"id": "help", "label": "Помоги", "kind": "ask"}])
    loaded = ProactiveInbox(tmp_path / "inbox.json").list()[0]
    assert item["proposals"] == loaded["proposals"]
