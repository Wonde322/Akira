import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALID_PERMISSION_LEVELS = {"auto", "confirm", "blocked"}


def tool_names(brain):
    return [tool["function"]["name"] for tool in brain.TOOLS]


def test_tool_descriptions_and_implementations_are_in_one_to_one_mapping(
    isolated_project,
):
    brain = isolated_project("brain")
    names = tool_names(brain)

    assert len(names) == len(set(names))
    assert set(names) == set(brain.FUNCTIONS)


def test_committed_permission_mapping_covers_every_registered_tool(
    isolated_project,
):
    brain = isolated_project("brain")
    committed_permissions = json.loads(
        (ROOT / "permissions.json").read_text(encoding="utf-8")
    )

    assert set(tool_names(brain)) <= set(committed_permissions)
    assert set(committed_permissions.values()) <= VALID_PERMISSION_LEVELS


def test_default_permissions_always_resolve_to_a_valid_level(isolated_project):
    brain = isolated_project("brain")
    permissions = isolated_project("permissions")

    assert set(permissions.DEFAULT_PERMISSIONS.values()) <= VALID_PERMISSION_LEVELS
    assert {
        permissions.get_permission(name) for name in tool_names(brain)
    } <= VALID_PERMISSION_LEVELS


def test_tools_without_explicit_default_use_confirmation_fallback(isolated_project):
    brain = isolated_project("brain")
    permissions = isolated_project("permissions")
    tools_without_default = set(tool_names(brain)) - set(
        permissions.DEFAULT_PERMISSIONS
    )

    assert tools_without_default == {
        "analyze_goals",
        "check_proactive",
        "find_files",
        "open_youtube",
        "play_spotify",
    }
    assert {
        permissions.get_permission(name) for name in tools_without_default
    } == {"confirm"}
