from datetime import datetime, timedelta, timezone

from awareness import AwarenessRuntime
from goal_context import GoalContextLinker, GoalStore, PRIORITY_WEIGHTS


def make_store(tmp_path):
    return GoalStore(tmp_path / "goals.json")


def test_create_goal_defaults_to_normal(tmp_path):
    result = make_store(tmp_path).create("Finish Figma layout")
    assert result["success"] and result["goal"]["priority"] == "normal"


def test_empty_goal_is_rejected(tmp_path):
    assert make_store(tmp_path).create("   ")["error"] == "empty_goal"


def test_invalid_priority_is_rejected(tmp_path):
    assert make_store(tmp_path).create("x", priority="urgent")["error"] == "invalid_priority"


def test_invalid_deadline_is_rejected(tmp_path):
    assert make_store(tmp_path).create("x", deadline="tomorrow")["error"] == "invalid_deadline"


def test_goal_persists_across_reload(tmp_path):
    path = tmp_path / "goals.json"
    created = GoalStore(path).create("Portfolio", priority="high")["goal"]
    loaded = GoalStore(path).list()
    assert loaded[0]["id"] == created["id"] and loaded[0]["priority"] == "high"


def test_list_prefers_higher_priority(tmp_path):
    store = make_store(tmp_path)
    store.create("low", priority="low")
    store.create("critical", priority="critical")
    assert store.list()[0]["title"] == "critical"


def test_terminal_goals_hidden_by_default(tmp_path):
    store = make_store(tmp_path)
    goal = store.create("done")["goal"]
    store.update(goal["id"], status="completed")
    assert store.list() == []
    assert len(store.list(include_terminal=True)) == 1


def test_update_priority_and_status(tmp_path):
    store = make_store(tmp_path)
    goal = store.create("x")["goal"]
    updated = store.update(goal["id"], priority="high", status="paused")["goal"]
    assert updated["priority"] == "high" and updated["status"] == "paused"


def test_update_missing_goal(tmp_path):
    assert make_store(tmp_path).update("missing", priority="high")["error"] == "goal_not_found"


def test_update_invalid_priority_keeps_goal_valid(tmp_path):
    store = make_store(tmp_path); goal = store.create("x")["goal"]
    assert store.update(goal["id"], priority="bad")["error"] == "invalid_priority"
    assert store.list()[0]["priority"] == "normal"


def test_context_match_uses_desktop_tokens(tmp_path):
    store = make_store(tmp_path)
    store.create("Finish Figma portfolio layout", priority="high")
    match = GoalContextLinker(store).match({"app": "Figma", "title": "Portfolio layout"})
    assert match and match["priority"] == "high" and match["confidence"] > 0


def test_unrelated_context_returns_none(tmp_path):
    store = make_store(tmp_path); store.create("Cook dinner")
    assert GoalContextLinker(store).match({"app": "Figma", "title": "Portfolio"}) is None


def test_explicit_task_link_is_strong_match(tmp_path):
    store = make_store(tmp_path)
    store.create("Something else", task_id="task-1")
    match = GoalContextLinker(store).match({}, {"task_id": "task-1", "goal": "Figma work"})
    assert match and match["confidence"] == 1.0


def test_urgent_deadline_increases_urgency(tmp_path):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    store = make_store(tmp_path)
    store.create("Figma", priority="low", deadline=(now + timedelta(hours=2)).isoformat())
    linker = GoalContextLinker(store, now=now)
    assert linker.match({"app": "Figma"})["urgency"] >= 0.95


def test_overdue_goal_is_maximum_urgency(tmp_path):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    store = make_store(tmp_path)
    store.create("Figma", deadline=(now - timedelta(minutes=1)).isoformat())
    assert GoalContextLinker(store, now=now).match({"app": "Figma"})["urgency"] == 1.0


def test_later_deadline_keeps_priority_urgency(tmp_path):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    store = make_store(tmp_path)
    store.create("Figma", priority="high", deadline=(now + timedelta(days=10)).isoformat())
    assert GoalContextLinker(store, now=now).match({"app": "Figma"})["urgency"] == PRIORITY_WEIGHTS["high"]


class FakePatterns:
    def observe(self, ui):
        return [{"type": "desktop.context.repeated", "context": ui}]


class FakeTaskLinker:
    def match(self, context):
        return {"task_id": "t1", "goal": "Finish Figma portfolio", "confidence": 0.8}


class FakeGoalLinker:
    def match(self, context, active_task=None):
        assert active_task["task_id"] == "t1"
        return {"goal_id": "g1", "title": "Finish portfolio", "priority": "high", "confidence": 0.9, "urgency": 0.8}


def test_awareness_enriches_pattern_with_task_and_goal(tmp_path, monkeypatch):
    monkeypatch.setattr("awareness.STATE_FILE", tmp_path / "awareness.json")
    runtime = AwarenessRuntime(pattern_engine=FakePatterns(), task_context_linker=FakeTaskLinker(), goal_context_linker=FakeGoalLinker())
    item = runtime._enrich_pattern({"type": "x", "context": {"app": "Figma"}})
    assert item["active_task"]["task_id"] == "t1"
    assert item["active_goal"]["priority"] == "high"


def test_awareness_survives_goal_linker_failure(tmp_path, monkeypatch):
    class BrokenGoal:
        def match(self, *args, **kwargs): raise RuntimeError("broken")
    monkeypatch.setattr("awareness.STATE_FILE", tmp_path / "awareness.json")
    runtime = AwarenessRuntime(pattern_engine=FakePatterns(), task_context_linker=FakeTaskLinker(), goal_context_linker=BrokenGoal())
    item = runtime._enrich_pattern({"type": "x", "context": {"app": "Figma"}})
    assert "active_task" in item and "active_goal" not in item
