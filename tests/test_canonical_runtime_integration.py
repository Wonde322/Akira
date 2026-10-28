from types import SimpleNamespace

import pytest

from agent_runtime import AgentRuntime
from akira_gateway import AkiraGateway


def message(content=None, calls=None):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=calls))])


def tool_call(name, arguments):
    return SimpleNamespace(id="call-1", function=SimpleNamespace(name=name, arguments=arguments))


def test_gateway_runs_canonical_model_tool_and_followup_in_same_session(isolated_project, monkeypatch):
    loop = isolated_project("agent_loop")
    actions, turns = [], []
    responses = iter([
        message(calls=[tool_call("set_volume", '{"level": 25}')]),
        message("Громкость установлена."),
        message("Продолжаем."),
    ])

    def create(**kwargs):
        turns.append(list(kwargs["messages"]))
        return next(responses)

    monkeypatch.setattr(loop, "client", SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    monkeypatch.setattr(loop, "build_memory_context", lambda *args, **kwargs: "")
    monkeypatch.setattr(loop, "get_permission", lambda name: "auto")
    monkeypatch.setattr(loop, "get_tool_implementation", lambda name: lambda **args: actions.append((name, args)) or {"success": True, "output": "25"})
    gateway = AkiraGateway(AgentRuntime())
    assert gateway.submit_text("громкость 25", metadata={"session_id": "integration"}) == "Громкость установлена."
    assert gateway.submit_text("продолжаем", metadata={"session_id": "integration"}) == "Продолжаем."
    assert actions == [("set_volume", {"level": 25})]
    assert any(item.get("role") == "tool" for item in turns[1])
    assert any(item.get("content") == "Громкость установлена." for item in turns[2])
    assert loop.get_session("integration").task is None


def test_runtime_cancel_during_model_response_blocks_real_tool_dispatch(isolated_project, monkeypatch):
    loop = isolated_project("agent_loop")
    runtime = AgentRuntime()
    calls = []

    def create(**kwargs):
        assert runtime.cancel("cancel-integration")
        return message(calls=[tool_call("set_volume", '{"level": 25}')])

    monkeypatch.setattr(loop, "client", SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    monkeypatch.setattr(loop, "build_memory_context", lambda *args, **kwargs: "")
    monkeypatch.setattr(loop, "get_tool_implementation", lambda name: lambda **args: calls.append(name))
    result = AkiraGateway(runtime).submit_text("test", request_id="cancel-integration")
    assert result["error"] == "cancelled"
    assert calls == []
    assert not runtime.is_active("cancel-integration")


def test_model_error_does_not_leave_an_old_computer_task_active(isolated_project, monkeypatch):
    loop = isolated_project("agent_loop")
    session = loop.get_session("failed-turn")
    session.begin_task("old computer goal")

    def create(**kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(loop, "client", SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    monkeypatch.setattr(loop, "build_memory_context", lambda *args, **kwargs: "")
    monkeypatch.setattr(loop, "_tools_for_reasoning", lambda **kwargs: [])
    with pytest.raises(RuntimeError, match="provider unavailable"):
        AkiraGateway(AgentRuntime()).submit_text("test", metadata={"session_id": session.session_id})
    assert session.task is None
