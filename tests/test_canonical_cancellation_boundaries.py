from threading import Event
from types import SimpleNamespace

import pytest


@pytest.fixture
def cancelled_turn(isolated_project):
    loop = isolated_project("agent_loop")
    import execution_context as execution

    event = Event()
    token = execution.activate_execution(execution.ExecutionContext(
        goal="test", session_id="test", mode="auto", _cancel_event=event,
    ))
    try:
        yield loop, execution, event
    finally:
        execution.deactivate_execution(token)


def test_cancel_during_model_call_prevents_tool_execution(cancelled_turn, monkeypatch):
    loop, execution, event = cancelled_turn
    calls = []

    def create(**kwargs):
        event.set()
        tool = SimpleNamespace(id="call-1", function=SimpleNamespace(name="test_action", arguments="{}"))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content=None, tool_calls=[tool],
        ))])

    monkeypatch.setattr(loop, "client", SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    monkeypatch.setattr(loop, "build_memory_context", lambda *a, **k: "")
    monkeypatch.setattr(loop, "_tools_for_reasoning", lambda **k: [])
    monkeypatch.setattr(loop, "_execute_and_audit", lambda *a, **k: calls.append(a) or {"success": True, "output": "ok"})

    with pytest.raises(execution.ExecutionCancelled):
        loop.ask("test", session_id="cancel-test")
    assert calls == []


def test_cancel_during_confirmation_prevents_action(cancelled_turn, monkeypatch):
    loop, execution, event = cancelled_turn
    calls = []
    monkeypatch.setattr(loop, "get_tool_implementation", lambda name: lambda: calls.append(name))
    monkeypatch.setattr(loop, "get_permission", lambda name: "confirm")

    def confirm(*args):
        event.set()
        return True

    monkeypatch.setattr(loop, "request_confirmation", confirm)
    with pytest.raises(execution.ExecutionCancelled):
        loop._execute("test_action", {})
    assert calls == []


def test_cancelled_tool_exception_is_not_converted_to_tool_error(cancelled_turn, monkeypatch):
    loop, execution, event = cancelled_turn

    def action():
        event.set()
        execution.raise_if_execution_cancelled()

    monkeypatch.setattr(loop, "get_tool_implementation", lambda name: action)
    monkeypatch.setattr(loop, "get_permission", lambda name: "auto")
    with pytest.raises(execution.ExecutionCancelled):
        loop._execute("test_action", {})


def test_cancel_before_observation_skips_capture(cancelled_turn, monkeypatch):
    loop, execution, event = cancelled_turn
    import capabilities.observe as observation
    calls = []
    monkeypatch.setattr(observation, "observe", lambda **k: calls.append(k))
    event.set()
    with pytest.raises(execution.ExecutionCancelled):
        loop._inject_observation(None, [], [])
    assert calls == []


def test_worker_suppresses_cancelled_result_output():
    from desktop_app.worker import _response_text
    assert _response_text({"success": False, "error": "cancelled", "output": "Выполнение отменено."}) == ""


def test_cancelled_turn_clears_unfinished_computer_task(cancelled_turn, monkeypatch):
    loop, execution, event = cancelled_turn
    session = loop.get_session("cancelled-computer-task")
    session.begin_task("old goal")
    event.set()
    with pytest.raises(execution.ExecutionCancelled):
        loop.ask("new goal", session_id=session.session_id)
    assert session.task is None


def test_unknown_canonical_tool_does_not_prompt(cancelled_turn, monkeypatch):
    loop, execution, event = cancelled_turn
    monkeypatch.setattr(loop, "get_tool_implementation", lambda name: None)
    monkeypatch.setattr(loop, "resolve_capability", lambda name: {"success": False})

    def unexpected_permission(*args):
        raise AssertionError("Unknown tools cannot ask for permission")

    monkeypatch.setattr(loop, "get_permission", unexpected_permission)
    result, decision = loop._execute("missing_tool", {})
    assert result["error"] == "unknown"
    assert decision == "unknown"
