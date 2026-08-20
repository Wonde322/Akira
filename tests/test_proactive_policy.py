from proactive_policy import ProactiveReasoningPolicy
from proactive_runtime import ProactiveAction, ProactiveRuntime


def task(goal="Исправить Figma макет", confidence=0.9):
    return {"goal": goal, "confidence": confidence, "status": "running"}


def event(event_type, payload):
    return {"id": "policy-test", "type": event_type, "payload": payload}


def test_weak_task_context_stays_quiet():
    policy = ProactiveReasoningPolicy()
    result = policy.decide("desktop.context.repeated", {"count": 4, "active_task": task(confidence=0.2)})
    assert result.action == "record"
    assert result.reason == "weak_task_context"


def test_strong_repeated_context_asks_user():
    policy = ProactiveReasoningPolicy()
    result = policy.decide("desktop.context.repeated", {"count": 3, "active_task": task(confidence=0.8)})
    assert result.action == "ask_user"
    assert "Исправить Figma макет" in result.notification


def test_medium_repeated_context_only_notifies():
    policy = ProactiveReasoningPolicy()
    result = policy.decide("desktop.context.repeated", {"count": 3, "active_task": task(confidence=0.5)})
    assert result.action == "notify"
    assert result.priority == "low"


def test_long_high_confidence_dwell_asks_user():
    policy = ProactiveReasoningPolicy(long_dwell_seconds=100)
    result = policy.decide("desktop.context.dwell", {"seconds": 120, "active_task": task(confidence=0.9)})
    assert result.action == "ask_user"
    assert "помогу" in result.notification


def test_runtime_uses_reasoning_policy_for_linked_pattern():
    runtime = ProactiveRuntime(dedupe_seconds=0)
    decision = runtime.decide(event("desktop.context.repeated", {"count": 3, "active_task": task(confidence=0.9)}))
    assert decision.action == ProactiveAction.ASK_USER
    assert decision.source == "context_reasoning"
    assert decision.reason == "repeated_task_context"
