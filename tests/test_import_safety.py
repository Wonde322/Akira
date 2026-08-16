import pytest


@pytest.mark.parametrize(
    "module_name",
    [
        "memory",
        "permissions",
        "tools",
        "activity_stats",
        "analysis",
        "audit",
        "config",
        "format",
        "session",
        "spotify_control",
        "tool_registry",
        "youtube",
        "brain",
        "capabilities.apps",
        "capabilities.backend",
        "capabilities.filesystem",
        "capabilities.gui",
        "capabilities.key",
        "capabilities.observe",
        "capabilities.observation",
        "capabilities.protocol",
        "capabilities.shell",
        "capabilities.task",
        "capabilities.vision",
        "capabilities.wait",
    ],
)
def test_safe_modules_import_without_external_calls(isolated_project, module_name):
    """These imports use a fake Groq module and do not start a service/device."""
    module = isolated_project(module_name)

    assert module is not None
