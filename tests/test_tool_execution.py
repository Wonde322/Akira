import builtins


def test_blocked_tool_is_not_called(isolated_project, monkeypatch):
    agent_loop = isolated_project("agent_loop")
    called = []
    monkeypatch.setattr(agent_loop, "get_tool_implementation", lambda _: lambda: called.append(True))
    monkeypatch.setattr(agent_loop, "get_permission", lambda _: "blocked")

    result, decision = agent_loop._execute("action", {})

    assert result == {
        "success": False,
        "error": "blocked",
        "output": "Инструмент заблокирован настройками разрешений.",
    }
    assert decision == "blocked"
    assert called == []


def test_confirmation_denial_is_not_called(isolated_project, monkeypatch):
    agent_loop = isolated_project("agent_loop")
    called = []
    monkeypatch.setattr(agent_loop, "get_tool_implementation", lambda _: lambda: called.append(True))
    monkeypatch.setattr(agent_loop, "get_permission", lambda _: "confirm")
    monkeypatch.setattr(builtins, "input", lambda _: "нет")

    result, decision = agent_loop._execute("action", {})

    assert result == {
        "success": False,
        "error": "denied",
        "output": "Пользователь не разрешил выполнение действия.",
    }
    assert decision == "denied"
    assert called == []


def test_confirmation_acceptance_calls_tool_with_arguments(isolated_project, monkeypatch):
    agent_loop = isolated_project("agent_loop")
    monkeypatch.setattr(
        agent_loop,
        "get_tool_implementation",
        lambda _: lambda value: f"done: {value}",
    )
    monkeypatch.setattr(agent_loop, "get_permission", lambda _: "confirm")
    monkeypatch.setattr(builtins, "input", lambda _: "да")

    result, decision = agent_loop._execute("action", {"value": "ok"})

    assert result["success"] is True
    assert result["output"] == "done: ok"
    assert result["requested_tool"] == "action"
    assert result["resolved_tool"] == "action"
    assert decision == "confirmed"


def test_tool_exception_is_returned_as_a_safe_error(isolated_project, monkeypatch):
    agent_loop = isolated_project("agent_loop")

    def failing_action():
        raise RuntimeError("failure")

    monkeypatch.setattr(agent_loop, "get_tool_implementation", lambda _: failing_action)
    monkeypatch.setattr(agent_loop, "get_permission", lambda _: "auto")

    result, decision = agent_loop._execute("action", {})

    assert result == {
        "success": False,
        "error": "error",
        "output": "Ошибка выполнения инструмента: failure",
    }
    assert decision == "auto"


def test_unknown_tool_is_not_executed(isolated_project, monkeypatch):
    agent_loop = isolated_project("agent_loop")
    monkeypatch.setattr(agent_loop, "get_permission", lambda _: "auto")
    monkeypatch.setattr(agent_loop, "get_tool_implementation", lambda _: None)
    monkeypatch.setattr(agent_loop, "resolve_capability", lambda _: {"success": False})

    result, decision = agent_loop._execute("missing", {})

    assert result == {
        "success": False,
        "error": "unknown",
        "output": "Неизвестный инструмент.",
    }
    assert decision == "auto"
