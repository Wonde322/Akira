import pytest

from proactive_e2e import ProactiveScenarioRunner


def make_emit(results=None):
    calls = []
    queue = list(results or [])
    def emit(event_type, payload, **metadata):
        calls.append((event_type, payload, metadata))
        result = queue.pop(0) if queue else {"success": True}
        result = dict(result)
        result.setdefault("success", True)
        result.setdefault("event", {"id": f"e{len(calls)}", "type": event_type, "payload": payload})
        return result
    return emit, calls


def test_single_event_is_successful():
    emit, _ = make_emit()
    result = ProactiveScenarioRunner(emit=emit).run([{"type": "desktop.context.repeated"}], "s1")
    assert result["success"] is True
    assert result["scenario_id"] == "s1"
    assert len(result["steps"]) == 1


def test_payload_is_forwarded_unchanged():
    emit, calls = make_emit()
    payload = {"count": 3, "active_task": {"goal": "Fix layout"}}
    ProactiveScenarioRunner(emit=emit).run([{"type": "desktop.context.repeated", "payload": payload}], "s1")
    assert calls[0][1] == payload


def test_correlation_id_is_shared_by_all_steps():
    emit, calls = make_emit()
    ProactiveScenarioRunner(emit=emit).run([{"type": "a"}, {"type": "b"}, {"type": "c"}], "flow")
    assert [call[2]["correlation_id"] for call in calls] == ["flow", "flow", "flow"]


def test_first_step_has_no_parent():
    emit, calls = make_emit()
    ProactiveScenarioRunner(emit=emit).run([{"type": "a"}], "flow")
    assert calls[0][2]["parent_event_id"] is None
    assert calls[0][2]["causation_depth"] == 0


def test_following_step_uses_previous_event_as_parent():
    emit, calls = make_emit([{"event": {"id": "first"}}, {"event": {"id": "second"}}])
    ProactiveScenarioRunner(emit=emit).run([{"type": "a"}, {"type": "b"}], "flow")
    assert calls[1][2]["parent_event_id"] == "first"
    assert calls[1][2]["causation_depth"] == 1


def test_explicit_metadata_can_override_defaults():
    emit, calls = make_emit()
    ProactiveScenarioRunner(emit=emit).run([{"type": "a", "metadata": {"source": "test", "causation_depth": 2}}], "flow")
    assert calls[0][2]["source"] == "test"
    assert calls[0][2]["causation_depth"] == 2


def test_default_source_marks_e2e_runner():
    emit, calls = make_emit()
    ProactiveScenarioRunner(emit=emit).run([{"type": "a"}], "flow")
    assert calls[0][2]["source"] == "proactive.e2e"


def test_decision_is_exposed_in_trace():
    emit, _ = make_emit([{"decision": {"action": "ask_user", "reason": "repeated_task_context"}}])
    result = ProactiveScenarioRunner(emit=emit).run([{"type": "desktop.context.repeated"}])
    assert result["steps"][0]["decision"]["action"] == "ask_user"


def test_spawn_task_scenario_is_visible():
    emit, _ = make_emit([{"decision": {"action": "spawn_task"}, "launched": [{"task_id": "t1"}]}])
    result = ProactiveScenarioRunner(emit=emit).run([{"type": "schedule.due", "payload": {"goal": "check"}}])
    assert result["steps"][0]["result"]["launched"][0]["task_id"] == "t1"


def test_completion_can_follow_spawn_in_same_trace():
    emit, _ = make_emit([
        {"event": {"id": "scheduled"}, "decision": {"action": "spawn_task"}},
        {"event": {"id": "completed"}, "decision": {"action": "notify"}},
    ])
    result = ProactiveScenarioRunner(emit=emit).run([
        {"type": "schedule.due", "payload": {"goal": "inspect"}},
        {"type": "task.completed", "payload": {"task_id": "t1", "notify": True}},
    ], "flow")
    assert [step["decision"]["action"] for step in result["steps"]] == ["spawn_task", "notify"]


def test_failed_step_makes_scenario_unsuccessful():
    emit, _ = make_emit([{"success": True}, {"success": False, "error": "boom"}])
    result = ProactiveScenarioRunner(emit=emit).run([{"type": "a"}, {"type": "b"}])
    assert result["success"] is False


def test_runner_continues_after_failed_step_for_full_trace():
    emit, calls = make_emit([{"success": False}, {"success": True}])
    result = ProactiveScenarioRunner(emit=emit).run([{"type": "a"}, {"type": "b"}])
    assert len(calls) == 2
    assert len(result["steps"]) == 2


def test_missing_type_is_rejected():
    emit, _ = make_emit()
    with pytest.raises(ValueError, match="scenario_step_requires_type"):
        ProactiveScenarioRunner(emit=emit).run([{}])


def test_non_mapping_step_is_rejected():
    emit, _ = make_emit()
    with pytest.raises(ValueError, match="scenario_step_must_be_mapping"):
        ProactiveScenarioRunner(emit=emit).run(["desktop.changed"])


def test_result_event_without_id_does_not_create_invalid_parent():
    emit, calls = make_emit([{"event": {}}, {"event": {"id": "second"}}])
    ProactiveScenarioRunner(emit=emit).run([{"type": "a"}, {"type": "b"}])
    assert calls[1][2]["parent_event_id"] is None


def test_step_indexes_are_stable():
    emit, _ = make_emit()
    result = ProactiveScenarioRunner(emit=emit).run([{"type": "a"}, {"type": "b"}, {"type": "c"}])
    assert [step["index"] for step in result["steps"]] == [0, 1, 2]


def test_empty_scenario_is_successful():
    emit, calls = make_emit()
    result = ProactiveScenarioRunner(emit=emit).run([], "empty")
    assert result["success"] is True
    assert result["steps"] == []
    assert calls == []
