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
    "close_app",
    "complete_task",
    "delete_file",
    "find_files",
    "get_goals",
    "get_recent_events",
    "get_running_apps",
    "get_tasks",
    "get_volume",
    "mute_volume",
    "open_app",
    "open_youtube",
    "play_spotify",
    "set_volume",
}


def test_registry_contains_all_existing_tools_once(isolated_project):
    registry = isolated_project("tool_registry")
    names = [tool.name for tool in registry.TOOL_REGISTRY]

    assert len(names) == 20
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


def test_committed_permission_mapping_covers_every_registered_tool(
    isolated_project,
):
    registry = isolated_project("tool_registry")
    committed_permissions = json.loads(
        (ROOT / "permissions.json").read_text(encoding="utf-8")
    )

    assert {tool.name for tool in registry.TOOL_REGISTRY} <= set(
        committed_permissions
    )
    assert set(committed_permissions.values()) <= VALID_PERMISSION_LEVELS


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
