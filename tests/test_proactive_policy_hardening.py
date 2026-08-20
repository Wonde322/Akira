from proactive_policy_guard import ProactivePolicyGuard
from proactive_runtime import ProactiveAction, ProactiveDecision


def event(event_type="desktop.context.repeated", **payload):
    return {"id": "event", "type": event_type, "payload": payload}


def decision(priority="normal", reason="repeated_task_context"):
    return ProactiveDecision(ProactiveAction.NOTIFY, reason, priority=priority)


def test_first_event_is_allowed():
    guard = ProactivePolicyGuard(clock=lambda: 10)
    assert guard.check(event(), decision()) == (True, "allowed")


def test_same_semantic_event_is_suppressed_inside_cooldown():
    now = [10.0]
    guard = ProactivePolicyGuard(clock=lambda: now[0])
    guard.check(event(goal="A"), decision())
    now[0] += 10
    assert guard.check(event(goal="A"), decision()) == (False, "policy_cooldown")


def test_event_is_allowed_after_cooldown():
    now = [10.0]
    guard = ProactivePolicyGuard(cooldown_seconds=30, clock=lambda: now[0])
    guard.check(event(goal="A"), decision())
    now[0] += 31
    assert guard.check(event(goal="A"), decision()) == (True, "allowed")


def test_higher_priority_escalates_inside_cooldown():
    guard = ProactivePolicyGuard(clock=lambda: 10)
    guard.check(event(goal="A"), decision("normal"))
    assert guard.check(event(goal="A"), decision("high")) == (True, "priority_escalation")


def test_equal_priority_does_not_escalate():
    guard = ProactivePolicyGuard(clock=lambda: 10)
    guard.check(event(goal="A"), decision("high"))
    assert guard.check(event(goal="A"), decision("high")) == (False, "policy_cooldown")


def test_lower_priority_is_suppressed_after_higher_priority():
    guard = ProactivePolicyGuard(clock=lambda: 10)
    guard.check(event(goal="A"), decision("critical"))
    assert guard.check(event(goal="A"), decision("low")) == (False, "policy_cooldown")


def test_different_goals_do_not_conflict():
    guard = ProactivePolicyGuard(clock=lambda: 10)
    guard.check(event(goal="A"), decision())
    assert guard.check(event(goal="B"), decision()) == (True, "allowed")


def test_different_contexts_do_not_conflict():
    guard = ProactivePolicyGuard(clock=lambda: 10)
    guard.check(event(app="Figma", title="A"), decision())
    assert guard.check(event(app="Chrome", title="A"), decision()) == (True, "allowed")


def test_active_task_goal_is_part_of_semantic_identity():
    guard = ProactivePolicyGuard(clock=lambda: 10)
    first = event(active_task={"goal": "Макет"})
    second = event(active_task={"goal": "Отчёт"})
    guard.check(first, decision())
    assert guard.check(second, decision()) == (True, "allowed")


def test_state_survives_restart(tmp_path):
    path = tmp_path / "guard.json"
    first = ProactivePolicyGuard(path, clock=lambda: 100)
    first.check(event(goal="A"), decision())
    second = ProactivePolicyGuard(path, clock=lambda: 120)
    assert second.check(event(goal="A"), decision()) == (False, "policy_cooldown")


def test_corrupt_state_falls_back_to_empty(tmp_path):
    path = tmp_path / "guard.json"
    path.write_text("not-json", encoding="utf-8")
    guard = ProactivePolicyGuard(path, clock=lambda: 10)
    assert guard.check(event(), decision()) == (True, "allowed")


def test_pruning_removes_old_entries(tmp_path):
    now = [0.0]
    guard = ProactivePolicyGuard(tmp_path / "guard.json", cooldown_seconds=10, clock=lambda: now[0])
    guard.check(event(goal="old"), decision())
    now[0] = 400
    guard.check(event(goal="new"), decision())
    assert len(guard._entries) == 1


def test_reset_clears_persisted_state(tmp_path):
    path = tmp_path / "guard.json"
    guard = ProactivePolicyGuard(path, clock=lambda: 10)
    guard.check(event(), decision())
    guard.reset()
    fresh = ProactivePolicyGuard(path, clock=lambda: 10)
    assert fresh.check(event(), decision()) == (True, "allowed")


def test_semantic_key_is_stable_for_payload_order():
    one = event(goal="A", app="Figma")
    two = {"type": "desktop.context.repeated", "id": "other", "payload": {"app": "Figma", "goal": "A"}}
    assert ProactivePolicyGuard.semantic_key(one, decision()) == ProactivePolicyGuard.semantic_key(two, decision())


def test_reason_isolated_when_context_is_same():
    guard = ProactivePolicyGuard(clock=lambda: 10)
    guard.check(event(goal="A"), decision(reason="one"))
    assert guard.check(event(goal="A"), decision(reason="two")) == (True, "allowed")
