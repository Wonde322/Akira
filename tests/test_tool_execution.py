import builtins


def test_blocked_tool_is_not_called(isolated_project, monkeypatch):
    brain = isolated_project("brain")
    called = []
    brain.FUNCTIONS = {"action": lambda: called.append(True)}
    monkeypatch.setattr(brain, "get_permission", lambda _: "blocked")

    assert brain.execute_tool("action", {}) == (
        "Инструмент заблокирован настройками разрешений."
    )
    assert called == []


def test_confirmation_denial_is_not_called(isolated_project, monkeypatch):
    brain = isolated_project("brain")
    called = []
    brain.FUNCTIONS = {"action": lambda: called.append(True)}
    monkeypatch.setattr(brain, "get_permission", lambda _: "confirm")
    monkeypatch.setattr(builtins, "input", lambda _: "нет")

    assert brain.execute_tool("action", {}) == (
        "Пользователь не разрешил выполнение действия."
    )
    assert called == []


def test_confirmation_acceptance_calls_tool_with_arguments(
    isolated_project, monkeypatch
):
    brain = isolated_project("brain")
    brain.FUNCTIONS = {"action": lambda value: f"done: {value}"}
    monkeypatch.setattr(brain, "get_permission", lambda _: "confirm")
    monkeypatch.setattr(builtins, "input", lambda _: "да")

    assert brain.execute_tool("action", {"value": "ok"}) == "done: ok"


def test_tool_exception_is_returned_as_a_safe_error(isolated_project, monkeypatch):
    brain = isolated_project("brain")

    def failing_action():
        raise RuntimeError("failure")

    brain.FUNCTIONS = {"action": failing_action}
    monkeypatch.setattr(brain, "get_permission", lambda _: "auto")

    assert brain.execute_tool("action", {}) == "Ошибка выполнения инструмента: failure"


def test_unknown_tool_is_not_executed(isolated_project, monkeypatch):
    brain = isolated_project("brain")
    monkeypatch.setattr(brain, "get_permission", lambda _: "auto")

    assert brain.execute_tool("missing", {}) == "Неизвестный инструмент."
