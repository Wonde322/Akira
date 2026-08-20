from proactive_feedback import ProactiveFeedbackStore
from proactive_policy import ProactiveReasoningPolicy
from proactive_runtime import ProactiveAction, ProactiveRuntime


class FakeFeedback:
    def __init__(self, suppress=False):
        self.suppress = suppress
        self.calls = []
    def should_suppress_question(self, reason):
        self.calls.append(reason)
        return self.suppress


def task(confidence=0.9):
    return {"goal": "Исправить макет", "confidence": confidence, "status": "running"}


def test_feedback_counts_explicit_dismissals(tmp_path):
    store = ProactiveFeedbackStore(str(tmp_path / "feedback.json"), suppress_after=3)
    store.record("repeated_task_context", "dismiss")
    store.record("repeated_task_context", "dismiss")
    stats = store.stats("repeated_task_context")
    assert stats["dismissed"] == 2
    assert stats["accepted"] == 0
    assert not store.should_suppress_question("repeated_task_context")


def test_feedback_suppresses_after_repeated_unwanted_questions(tmp_path):
    store = ProactiveFeedbackStore(str(tmp_path / "feedback.json"), suppress_after=3)
    for _ in range(3): store.record("repeated_task_context", "dismiss")
    assert store.should_suppress_question("repeated_task_context")


def test_acceptance_prevents_dismissal_majority_suppression(tmp_path):
    store = ProactiveFeedbackStore(str(tmp_path / "feedback.json"), suppress_after=3)
    for _ in range(3): store.record("repeated_task_context", "dismiss")
    for _ in range(3): store.record("repeated_task_context", "ask")
    assert not store.should_suppress_question("repeated_task_context")


def test_feedback_survives_restart(tmp_path):
    path = str(tmp_path / "feedback.json")
    first = ProactiveFeedbackStore(path)
    first.record("long_task_dwell", "observe")
    second = ProactiveFeedbackStore(path)
    assert second.stats("long_task_dwell")["accepted"] == 1
    assert second.stats("long_task_dwell")["last_outcome"] == "accepted"


def test_policy_keeps_question_without_negative_feedback():
    feedback = FakeFeedback(False)
    policy = ProactiveReasoningPolicy(feedback_store=feedback)
    result = policy.decide("desktop.context.repeated", {"count": 3, "active_task": task()})
    assert result.action == "ask_user"
    assert feedback.calls == ["repeated_task_context"]


def test_policy_downgrades_repeatedly_dismissed_question():
    feedback = FakeFeedback(True)
    policy = ProactiveReasoningPolicy(feedback_store=feedback)
    result = policy.decide("desktop.context.repeated", {"count": 3, "active_task": task()})
    assert result.action == "notify"
    assert result.priority == "low"
    assert result.reason == "repeated_task_context_feedback_suppressed"


def test_policy_feedback_is_reason_specific():
    feedback = FakeFeedback(True)
    policy = ProactiveReasoningPolicy(long_dwell_seconds=1, feedback_store=feedback)
    result = policy.decide("desktop.context.dwell", {"seconds": 2, "active_task": task()})
    assert result.reason == "long_task_dwell_feedback_suppressed"
    assert feedback.calls == ["long_task_dwell"]


def test_runtime_uses_feedback_adjusted_policy():
    policy = ProactiveReasoningPolicy(feedback_store=FakeFeedback(True))
    runtime = ProactiveRuntime(dedupe_seconds=0, reasoning_policy=policy)
    decision = runtime.decide({"id": "feedback-runtime", "type": "desktop.context.repeated", "payload": {"count": 3, "active_task": task()}})
    assert decision.action == ProactiveAction.NOTIFY
    assert decision.reason.endswith("feedback_suppressed")
