from datetime import datetime, timezone

from awareness import AwarenessRuntime
from proactive_policy import ProactiveReasoningPolicy
from situation_context import SituationContextBuilder


class Feedback:
    def should_suppress_question(self, reason):
        return False


def fixed_clock():
    return datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)


def test_snapshot_preserves_desktop_context():
    snapshot = SituationContextBuilder(clock=fixed_clock).build({"app": "Figma", "title": "Layout"})
    assert snapshot["desktop"]["app"] == "Figma"


def test_snapshot_keeps_active_task():
    task = {"task_id": "t1", "goal": "Finish layout", "confidence": 0.8}
    snapshot = SituationContextBuilder(clock=fixed_clock).build(active_task=task)
    assert snapshot["active_task"]["task_id"] == "t1"


def test_snapshot_keeps_active_goal():
    goal = {"goal_id": "g1", "title": "Portfolio", "priority": "high", "urgency": 0.8}
    snapshot = SituationContextBuilder(clock=fixed_clock).build(active_goal=goal)
    assert snapshot["active_goal"]["goal_id"] == "g1"


def test_terminal_background_tasks_are_not_counted():
    builder = SituationContextBuilder(task_provider=lambda: [{"status": "completed"}, {"status": "running"}], clock=fixed_clock)
    assert builder.build()["background"]["active_count"] == 1


def test_cancelled_schedules_are_not_counted():
    builder = SituationContextBuilder(schedule_provider=lambda: [{"status": "cancelled"}, {"status": "pending"}], clock=fixed_clock)
    assert builder.build()["schedule"]["active_count"] == 1


def test_provider_failure_degrades_to_empty_context():
    def broken():
        raise RuntimeError("broken")
    snapshot = SituationContextBuilder(task_provider=broken, schedule_provider=broken, clock=fixed_clock).build()
    assert snapshot["background"]["active_count"] == 0 and snapshot["schedule"]["active_count"] == 0


def test_high_goal_produces_high_pressure():
    snapshot = SituationContextBuilder(clock=fixed_clock).build(active_goal={"priority": "high", "urgency": 0.2})
    assert snapshot["pressure"] == "high"


def test_critical_urgency_produces_critical_pressure():
    snapshot = SituationContextBuilder(clock=fixed_clock).build(active_goal={"priority": "low", "urgency": 1.0})
    assert snapshot["pressure"] == "critical"


def test_task_confidence_contributes_to_pressure():
    snapshot = SituationContextBuilder(clock=fixed_clock).build(active_task={"confidence": 1.0})
    assert snapshot["pressure"] == "normal"


def test_timestamp_is_normalized():
    assert SituationContextBuilder(clock=fixed_clock).build()["timestamp"] == "2026-08-20T12:00:00+00:00"


def test_goal_only_context_can_drive_repeated_notification():
    policy = ProactiveReasoningPolicy(feedback_store=Feedback())
    result = policy.decide("desktop.context.repeated", {"count": 2, "active_goal": {"title": "Portfolio", "priority": "normal", "urgency": 0.5}})
    assert result and result.goal == "Portfolio" and result.action == "notify"


def test_high_goal_elevates_low_signal_notification():
    policy = ProactiveReasoningPolicy(feedback_store=Feedback())
    result = policy.decide("desktop.context.repeated", {"count": 2, "active_task": {"goal": "Portfolio", "confidence": 0.5}, "active_goal": {"priority": "high", "urgency": 0.8}})
    assert result.priority == "normal"


def test_critical_goal_elevates_question_priority():
    policy = ProactiveReasoningPolicy(feedback_store=Feedback())
    result = policy.decide("desktop.context.repeated", {"count": 3, "active_task": {"goal": "Portfolio", "confidence": 0.9}, "active_goal": {"priority": "critical", "urgency": 0.5}})
    assert result.action == "ask_user" and result.priority == "high"


def test_goal_does_not_override_existing_task_goal_text():
    policy = ProactiveReasoningPolicy(feedback_store=Feedback())
    result = policy.decide("desktop.context.repeated", {"count": 3, "active_task": {"goal": "Task goal", "confidence": 0.9}, "active_goal": {"title": "Different goal", "priority": "normal", "urgency": 0.5}})
    assert result.goal == "Task goal"


def test_awareness_attaches_situation_snapshot(tmp_path, monkeypatch):
    class Patterns:
        def observe(self, ui):
            return []
    class Tasks:
        def match(self, context):
            return {"task_id": "t1", "goal": "Portfolio", "confidence": 0.8}
    class Goals:
        def match(self, context, active_task=None):
            return {"goal_id": "g1", "title": "Portfolio", "priority": "high", "urgency": 0.8}
    class Situation:
        def build(self, context, active_task, active_goal):
            return {"pressure": "high", "active_task": active_task, "active_goal": active_goal}
    monkeypatch.setattr("awareness.STATE_FILE", tmp_path / "state.json")
    runtime = AwarenessRuntime(pattern_engine=Patterns(), task_context_linker=Tasks(), goal_context_linker=Goals(), situation_builder=Situation())
    item = runtime._enrich_pattern({"type": "desktop.context.repeated", "context": {"app": "Figma"}})
    assert item["situation"]["pressure"] == "high"
