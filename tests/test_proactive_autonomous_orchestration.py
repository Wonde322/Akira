import sys
import types

from proactive_orchestrator import ProactiveOrchestrator
from proactive_runtime import ProactiveAction, ProactiveRuntime


class Clock:
    def __init__(self, value=0): self.value = value
    def __call__(self): return self.value


def payload(task_id="task-1", confidence=0.9, **extra):
    data = {
        "active_task": {"id": task_id, "goal": "Проверить макет", "status": "running", "confidence": confidence},
        "context": {"app": "Figma", "title": "Макет"},
    }
    data.update(extra)
    return data


def test_repeated_high_signal_spawns():
    o = ProactiveOrchestrator(clock=Clock())
    result = o.decide("desktop.context.repeated", payload(count=3))
    assert result["spawn"] is True
    assert result["task_id"] == "task-1"
    assert "не выполняй изменений" in result["goal"].lower()


def test_repeated_below_threshold_is_quiet():
    assert ProactiveOrchestrator().decide("desktop.context.repeated", payload(count=2))["spawn"] is False


def test_low_confidence_is_quiet():
    assert ProactiveOrchestrator().decide("desktop.context.repeated", payload(count=5, confidence=0.4))["reason"] == "insufficient_signal"


def test_missing_active_task_is_quiet():
    assert ProactiveOrchestrator().decide("desktop.context.repeated", {"count": 5})["spawn"] is False


def test_completed_source_task_is_ignored():
    data = payload(count=5)
    data["active_task"]["status"] = "completed"
    assert ProactiveOrchestrator().decide("desktop.context.repeated", data)["spawn"] is False


def test_dwell_high_signal_spawns():
    o = ProactiveOrchestrator(min_dwell_seconds=100)
    assert o.decide("desktop.context.dwell", payload(seconds=100))["spawn"] is True


def test_dwell_below_threshold_is_quiet():
    o = ProactiveOrchestrator(min_dwell_seconds=100)
    assert o.decide("desktop.context.dwell", payload(seconds=99))["spawn"] is False


def test_unrelated_event_is_quiet():
    assert ProactiveOrchestrator().decide("desktop.changed", payload())["spawn"] is False


def test_same_source_cannot_spawn_twice_while_active():
    o = ProactiveOrchestrator(clock=Clock())
    assert o.decide("desktop.context.repeated", payload(count=3))["spawn"]
    assert o.decide("desktop.context.repeated", payload(count=4))["reason"] == "task_already_active"


def test_release_allows_later_spawn_after_cooldown():
    clock = Clock()
    o = ProactiveOrchestrator(cooldown_seconds=10, clock=clock)
    assert o.decide("desktop.context.repeated", payload(count=3))["spawn"]
    o.release("task-1")
    assert o.decide("desktop.context.repeated", payload(count=4))["reason"] == "cooldown"
    clock.value = 10
    assert o.decide("desktop.context.repeated", payload(count=4))["spawn"]


def test_active_limit_blocks_second_source():
    o = ProactiveOrchestrator(max_active=1)
    assert o.decide("desktop.context.repeated", payload("a", count=3))["spawn"]
    assert o.decide("desktop.context.repeated", payload("b", count=3))["reason"] == "active_limit"


def test_runtime_prefers_autonomous_orchestration_over_question():
    clock = Clock()
    runtime = ProactiveRuntime(clock=clock, orchestrator=ProactiveOrchestrator(clock=clock))
    decision = runtime.decide({"id": "e1", "type": "desktop.context.repeated", "payload": payload(count=3)})
    assert decision.action == ProactiveAction.SPAWN_TASK
    assert decision.source == "autonomous_orchestration"
    assert decision.source_task_id == "task-1"


def test_runtime_keeps_low_signal_as_normal_policy():
    clock = Clock()
    runtime = ProactiveRuntime(clock=clock, orchestrator=ProactiveOrchestrator(clock=clock))
    decision = runtime.decide({"id": "e1", "type": "desktop.context.repeated", "payload": payload(count=3, confidence=0.2)})
    assert decision.action != ProactiveAction.SPAWN_TASK


def test_runtime_spawns_autonomous_task(monkeypatch):
    clock = Clock()
    runtime = ProactiveRuntime(clock=clock, orchestrator=ProactiveOrchestrator(clock=clock))
    class FakeRuntime:
        def spawn(self, goal, session_id):
            assert session_id.startswith("proactive:")
            return {"success": True, "task_id": "spawned-1"}
    monkeypatch.setitem(sys.modules, "task_runtime", types.SimpleNamespace(get_runtime=lambda: FakeRuntime()))
    result = runtime.handle({"id": "e1", "type": "desktop.context.repeated", "payload": payload(count=3)})
    assert result["launched"][0]["task_id"] == "spawned-1"
    assert runtime._orchestrator.active_source_tasks() == ["task-1"]


def test_runtime_releases_source_when_autonomous_task_completes(monkeypatch):
    clock = Clock()
    orchestrator = ProactiveOrchestrator(clock=clock)
    runtime = ProactiveRuntime(clock=clock, orchestrator=orchestrator)
    class FakeRuntime:
        def spawn(self, goal, session_id): return {"success": True, "task_id": "spawned-1"}
    monkeypatch.setitem(sys.modules, "task_runtime", types.SimpleNamespace(get_runtime=lambda: FakeRuntime()))
    runtime.handle({"id": "e1", "type": "desktop.context.repeated", "payload": payload(count=3)})
    runtime.handle({"id": "done", "type": "task.completed", "payload": {"task_id": "spawned-1", "session_id": "proactive:e1", "goal": "x", "result": "ok"}})
    assert orchestrator.active_source_tasks() == []


def test_spawn_failure_releases_source(monkeypatch):
    clock = Clock()
    orchestrator = ProactiveOrchestrator(clock=clock)
    runtime = ProactiveRuntime(clock=clock, orchestrator=orchestrator)
    monkeypatch.setitem(sys.modules, "task_runtime", types.SimpleNamespace(get_runtime=lambda: types.SimpleNamespace(spawn=lambda *a, **k: {"success": False})))
    runtime.handle({"id": "e1", "type": "desktop.context.repeated", "payload": payload(count=3)})
    assert orchestrator.active_source_tasks() == []
