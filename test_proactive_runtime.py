from proactive_runtime import ProactiveAction, ProactiveRuntime


def event(event_type, payload=None, depth=0):
    return {
        "id": "event-1",
        "type": event_type,
        "payload": payload or {},
        "causation_depth": depth,
    }


def test_schedule_due_spawns_task_decision():
    runtime = ProactiveRuntime()
    decision = runtime.decide(
        event("schedule.due", {"goal": "check something"})
    )
    assert decision.action == ProactiveAction.SPAWN_TASK
    assert decision.reason == "explicit_schedule"


def test_duplicate_event_is_ignored():
    runtime = ProactiveRuntime()
    first = runtime.decide(event("desktop.changed", {"app": "Figma"}))
    second = runtime.decide(event("desktop.changed", {"app": "Figma"}))
    assert first.action in {ProactiveAction.RECORD, ProactiveAction.SPAWN_TASK}
    assert second.action == ProactiveAction.IGNORE
    assert second.reason == "duplicate_event"


def test_desktop_cooldown_records_new_change():
    runtime = ProactiveRuntime(dedupe_seconds=0)
    runtime.decide(event("desktop.changed", {"app": "Figma"}))
    decision = runtime.decide(event("desktop.changed", {"app": "Chrome"}))
    assert decision.action == ProactiveAction.RECORD
    assert decision.reason == "desktop_cooldown"


def test_causation_depth_stops_chain():
    runtime = ProactiveRuntime(max_causation_depth=3)
    decision = runtime.decide(
        event("task.completed", depth=3),
        ["start another task"],
    )
    assert decision.action == ProactiveAction.IGNORE
    assert decision.reason == "max_causation_depth"


def test_trigger_goal_becomes_spawn_decision():
    runtime = ProactiveRuntime()
    decision = runtime.decide(
        event("custom.event", {"x": 1}),
        ["react to {{event.payload}}"],
    )
    assert decision.action == ProactiveAction.SPAWN_TASK
    assert decision.goal == "react to {{event.payload}}"
