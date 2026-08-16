import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALID_PERMISSION_LEVELS = {"auto", "confirm", "blocked"}
EXISTING_TOOL_NAMES = {
    "add_event",
    "add_goal",
    "add_task",
    "analyze_goals",
    "analyze_period",
    "check_proactive",
    "click",
    "close",
    "complete_task",
    "copy",
    "create",
    "delete",
    "drag",
    "find",
    "finish_task",
    "get_goals",
    "get_recent_events",
    "get_running_apps",
    "get_tasks",
    "get_volume",
    "key",
    "move",
    "mute_volume",
    "observe",
    "open",
    "open_youtube",
    "play_spotify",
    "read",
    "rename",
    "screen_size",
    "scroll",
    "select",
    "set_volume",
    "shell",
    "type",
    "wait",
    "write",
}


def test_registry_contains_all_existing_tools_once(isolated_project):
    registry = isolated_project("tool_registry")
    names = [tool.name for tool in registry.TOOL_REGISTRY]

    assert len(names) == 37
    assert len(names) == len(set(names))
    assert set(names) == EXISTING_TOOL_NAMES


def test_each_registry_entry_has_matching_schema_and_implementation(
    isolated_project,
):
    registry = isolated_project("tool_registry")

    for tool in registry.TOOL_REGISTRY:
        schema = tool.schema()

        assert tool.name
        assert tool.description
        assert tool.parameters["type"] == "object"
        assert schema["function"]["name"] == tool.name
        assert schema["function"]["parameters"] == tool.parameters
        assert callable(tool.implementation())


def test_brain_uses_registry_schemas_without_a_manual_implementation_map(
    isolated_project,
):
    brain = isolated_project("brain")
    registry = isolated_project("tool_registry")

    assert brain.TOOLS == registry.get_tool_schemas()
    assert not hasattr(brain, "FUNCTIONS")


def test_every_registry_tool_has_a_valid_permission_policy(isolated_project):
    registry = isolated_project("tool_registry")

    assert {
        tool.permission_policy for tool in registry.TOOL_REGISTRY
    } <= VALID_PERMISSION_LEVELS
    assert registry.get_default_tool_permissions() == {
        tool.name: tool.permission_policy for tool in registry.TOOL_REGISTRY
    }


def test_committed_permissions_match_registry_defaults(isolated_project):
    registry = isolated_project("tool_registry")
    committed_permissions = json.loads(
        (ROOT / "permissions.json").read_text(encoding="utf-8")
    )

    assert committed_permissions == registry.get_default_tool_permissions()


def test_committed_permissions_contain_no_non_existent_tools():
    committed_permissions = json.loads(
        (ROOT / "permissions.json").read_text(encoding="utf-8")
    )

    for name in committed_permissions:
        assert name in EXISTING_TOOL_NAMES


def test_default_permissions_are_derived_from_registry(isolated_project):
    permissions = isolated_project("permissions")
    registry = isolated_project("tool_registry")

    for tool in registry.TOOL_REGISTRY:
        assert permissions.DEFAULT_PERMISSIONS[tool.name] == tool.permission_policy

    assert permissions.get_permission("unknown_tool") == "confirm"


def test_no_legacy_independent_tool_lists_remain():
    brain_source = (ROOT / "brain.py").read_text(encoding="utf-8")
    permissions_source = (ROOT / "permissions.py").read_text(encoding="utf-8")

    assert "FUNCTIONS =" not in brain_source
    assert "\"open_app\":" not in permissions_source


def test_confirm_tool_is_denied_when_context_cannot_prompt(
    isolated_project, monkeypatch
):
    brain = isolated_project("brain")
    permissions = isolated_project("permissions")

    permissions.set_confirmation_provider(permissions.deny_all)
    monkeypatch.setattr(brain, "get_permission", lambda _: "confirm")

    called = []
    monkeypatch.setattr(
        brain,
        "get_tool_implementation",
        lambda _: lambda: called.append(True),
    )

    result = brain.execute_tool("action", {})

    assert result == "Пользователь не разрешил выполнение действия."
    assert called == []


def test_confirm_tool_never_auto_becomes_auto(isolated_project):
    registry = isolated_project("tool_registry")
    committed = json.loads(
        (ROOT / "permissions.json").read_text(encoding="utf-8")
    )

    for name, level in registry.get_default_tool_permissions().items():
        if level == "confirm":
            assert committed[name] == "confirm", name


def test_permissions_file_path_is_absolute_and_project_root(monkeypatch, tmp_path):
    import importlib
    import sys

    sys.modules.pop("permissions", None)
    monkeypatch.chdir(tmp_path)

    module = importlib.import_module("permissions")

    try:
        assert Path(module.PERMISSIONS_FILE).is_absolute()
        assert Path(module.PERMISSIONS_FILE).parent == ROOT
    finally:
        sys.modules.pop("permissions", None)


def test_web_server_disables_stdin_confirmation():
    source = (ROOT / "akira_server.py").read_text(encoding="utf-8")

    assert "set_confirmation_provider" in source
    assert "deny_all" in source


def test_voice_dialogue_disables_stdin_confirmation():
    source = (ROOT / "voice" / "dialogue.py").read_text(encoding="utf-8")

    assert "set_confirmation_provider" in source
    assert "deny_all" in source
