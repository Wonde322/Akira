import pytest


@pytest.mark.parametrize(
    "module_name",
    [
        "memory",
        "permissions",
        "file_tools",
        "tools",
        "activity_stats",
        "analysis",
        "goal_analysis",
        "proactive",
        "spotify_control",
        "tool_registry",
        "brain",
    ],
)
def test_safe_modules_import_without_external_calls(isolated_project, module_name):
    """These imports use a fake Groq module and do not start a service/device."""
    module = isolated_project(module_name)

    assert module is not None
