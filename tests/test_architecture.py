from pathlib import Path

import pytest

from permissions import PermissionManager


ROOT = Path(__file__).resolve().parents[1]


def test_registry_never_points_at_brain_for_implementations(isolated_project):
    registry = isolated_project("tool_registry")

    for tool in registry.TOOL_REGISTRY:
        assert tool.implementation_module != "brain", tool.name


def test_integration_tools_reside_in_their_own_modules(isolated_project):
    registry = isolated_project("tool_registry")
    definitions = {
        tool.name: (tool.implementation_module, tool.implementation_name)
        for tool in registry.TOOL_REGISTRY
    }

    assert definitions["open_youtube"] == ("youtube", "open_youtube")
    assert definitions["play_spotify"] == ("spotify_control", "play")
    assert definitions["analyze_goals"] == ("analysis", "analyze_goals")
    assert definitions["check_proactive"] == ("analysis", "check_proactive")
    assert definitions["analyze_period"] == ("analysis", "analyze_period")


def test_brain_does_not_contain_specialized_integrations():
    source = (ROOT / "brain.py").read_text(encoding="utf-8")

    assert "yt-dlp" not in source
    assert "CLIENT_ID" not in source
    assert "spotify" not in source.lower()
    assert "open -a" not in source


def test_youtube_module_does_not_depend_on_brain():
    source = (ROOT / "youtube.py").read_text(encoding="utf-8")

    assert "brain" not in source
    assert "yt-dlp" in source


def test_spotify_client_id_is_defined_once():
    control_source = (ROOT / "spotify_control.py").read_text(encoding="utf-8")
    auth_source = (ROOT / "spotify_auth.py").read_text(encoding="utf-8")

    assert "from spotify_control import CLIENT_ID" in auth_source
    assert control_source.count("71886dbe05744e1c9ea56d7ffd1eec1c") == 1
    assert auth_source.count("71886dbe05744e1c9ea56d7ffd1eec1c") == 0


def test_ask_records_audit_with_session_source(isolated_project, monkeypatch):
    brain = isolated_project("brain")

    monkeypatch.setattr(brain, "get_permission", lambda _: "auto")
    monkeypatch.setattr(brain, "get_tool_implementation", lambda _: lambda **kw: "ок")

    from types import SimpleNamespace


    class FakeToolCall:
        def __init__(self, id, name, arguments):
            self.id = id
            self.function = SimpleNamespace(name=name, arguments=arguments)


    class FakeMessage:
        def __init__(self, content=None, tool_calls=None):
            self.content = content
            self.tool_calls = tool_calls


    class FakeChoice:
        def __init__(self, message):
            self.message = message


    class FakeResponse:
        def __init__(self, message):
            self.choices = [FakeChoice(message)]


    responses = iter([
        FakeResponse(FakeMessage(tool_calls=[FakeToolCall("call-1", "open_app", "{}")])),
        FakeResponse(FakeMessage(content="готово")),
    ])

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kwargs: next(responses)
            )
        )
    )

    monkeypatch.setattr(brain, "client", fake_client)

    records = []
    monkeypatch.setattr(
        brain,
        "record_tool_execution",
        lambda *args, **kwargs: records.append((args, kwargs)),
    )

    brain.ask("открой Safari", session_id="web-1")

    assert records
    assert records[0][0][0] == "open_app"
    assert records[0][1]["source"] == "web-1"


def test_permission_manager_supports_per_context_providers(tmp_path):
    permission_file = str(tmp_path / "permissions.json")

    # Разные контексты могут использовать разные провайдеры.
    assert PermissionManager(permission_file, lambda *_: True).request_confirmation(
        "open_app", {}
    ) is True
    assert PermissionManager(permission_file, lambda *_: False).request_confirmation(
        "open_app", {}
    ) is False


def test_permission_manager_defaults_to_confirm(isolated_project):
    permissions = isolated_project("permissions")

    manager = PermissionManager(permissions.PERMISSIONS_FILE)

    assert manager.get_permission("unknown_tool") == "confirm"


def test_permission_manager_set_and_save(tmp_path):
    import json

    permission_file = str(tmp_path / "permissions.json")
    manager = PermissionManager(permission_file, confirmation_provider=lambda *_: False)

    result = manager.set_permission("open_app", "blocked")

    assert "blocked" in result
    assert manager.get_permission("open_app") == "blocked"

    stored = json.loads(
        (tmp_path / "permissions.json").read_text(encoding="utf-8")
    )
    assert stored["open_app"] == "blocked"


def test_permission_manager_rejects_invalid_levels(tmp_path):
    manager = PermissionManager(
        str(tmp_path / "permissions.json"),
        confirmation_provider=lambda *_: False,
    )

    result = manager.set_permission("delete_file", "bogus")

    assert "Недопустимый" in result
    assert manager.get_permission("delete_file") == "confirm"


def test_default_permission_manager_is_thread_safe(isolated_project):
    import threading

    permissions = isolated_project("permissions")

    results = []

    def worker():
        for _ in range(20):
            results.append(permissions.get_permission("read"))

    threads = [threading.Thread(target=worker) for _ in range(8)]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    assert results
    assert all(result == "auto" for result in results)