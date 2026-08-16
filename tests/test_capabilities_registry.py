import inspect
import json
import os


UNIVERSAL_TOOLS = {
    "observe",
    "screen_size",
    "open",
    "close",
    "find",
    "read",
    "write",
    "create",
    "move",
    "copy",
    "rename",
    "delete",
    "shell",
    "wait",
    "key",
    "select",
    "click",
    "type",
    "scroll",
    "drag",
}

AUTO_SAFE_TOOLS = {"observe", "screen_size", "read", "find", "wait"}

CONFIRM_DANGEROUS_TOOLS = {
    "open",
    "close",
    "write",
    "create",
    "move",
    "copy",
    "rename",
    "delete",
    "shell",
    "key",
    "select",
    "click",
    "type",
    "scroll",
    "drag",
}

BANNED_APP_SPECIFIC_NAMES = {
    "open_chrome",
    "open_photoshop",
    "open_calculator",
    "export_photoshop",
    "generate_castles",
    "run_specific_project",
    "click_spotify_button",
    "open_youtube_plus",
}


def test_universal_tools_are_registered(isolated_project):
    registry = isolated_project("tool_registry")

    names = {tool.name for tool in registry.TOOL_REGISTRY}

    assert UNIVERSAL_TOOLS <= names


def test_legacy_ad_hoc_tools_are_replaced(isolated_project):
    registry = isolated_project("tool_registry")

    names = {tool.name for tool in registry.TOOL_REGISTRY}

    assert not (names & {"open_app", "close_app", "find_files", "delete_file"})


def test_universal_tools_reside_in_capabilities_module(isolated_project):
    registry = isolated_project("tool_registry")

    for tool in registry.TOOL_REGISTRY:
        if tool.name in UNIVERSAL_TOOLS:
            assert tool.implementation_module.startswith("capabilities."), tool.name


def test_no_app_specific_tools_are_registered(isolated_project):
    registry = isolated_project("tool_registry")

    names = {tool.name for tool in registry.TOOL_REGISTRY}

    assert not (names & BANNED_APP_SPECIFIC_NAMES)


def test_safe_capabilities_are_auto(isolated_project):
    registry = isolated_project("tool_registry")

    for name in AUTO_SAFE_TOOLS:
        assert registry.get_default_tool_permissions()[name] == "auto", name


def test_dangerous_capabilities_are_confirm(isolated_project):
    registry = isolated_project("tool_registry")

    for name in CONFIRM_DANGEROUS_TOOLS:
        assert registry.get_default_tool_permissions()[name] == "confirm", name


def test_shell_is_never_auto(isolated_project):
    registry = isolated_project("tool_registry")

    assert registry.get_default_tool_permissions()["shell"] == "confirm"


def test_capability_schemas_match_implementation_signatures(isolated_project):
    registry = isolated_project("tool_registry")

    for tool in registry.TOOL_REGISTRY:
        if tool.name not in UNIVERSAL_TOOLS:
            continue

        implementation = tool.implementation()
        parameters = inspect.signature(implementation).parameters

        for prop in tool.parameters["properties"]:
            assert prop in parameters, f"{tool.name}: schema prop {prop} missing in signature"

        for required in tool.parameters.get("required", []):
            assert (
                parameters[required].default is inspect.Parameter.empty
            ), f"{tool.name}: required param {required} must not have a default"


def test_brain_passes_structured_results_through(isolated_project, monkeypatch):
    import capabilities.protocol as protocol

    brain = isolated_project("brain")

    monkeypatch.setattr(brain, "get_permission", lambda _: "auto")
    monkeypatch.setattr(
        brain,
        "get_tool_implementation",
        lambda _: lambda **kw: protocol.ok({"content": "hello"}),
    )

    result = brain.execute_tool_result("read", {"path": "/x"})

    assert result == protocol.ok({"content": "hello"})


def test_brain_tool_result_text_renders_structured(isolated_project):
    import capabilities.protocol as protocol

    brain = isolated_project("brain")

    text = brain._tool_result_text(protocol.ok({"content": "hello"}))

    assert "hello" in text
    assert "content" in text


def test_audit_records_structured_data(isolated_project):
    import capabilities.protocol as protocol

    audit = isolated_project("audit")

    audit.record_tool_execution(
        "read",
        {"path": "/x"},
        protocol.ok({"content": "hello"}),
        "auto",
        source="cli",
    )

    assert os.path.exists(audit.AUDIT_FILE)

    with open(audit.AUDIT_FILE, encoding="utf-8") as file:
        entry = json.loads(file.readline())

    assert entry["success"] is True
    assert entry["output"] == '{"content": "hello"}'
    assert entry["permission"] == "auto"


def test_audit_records_structured_failure_detail(isolated_project):
    import capabilities.protocol as protocol

    audit = isolated_project("audit")

    audit.record_tool_execution(
        "delete",
        {"path": "/x"},
        protocol.fail("not_allowed", "Путь запрещён."),
        "confirmed",
    )

    with open(audit.AUDIT_FILE, encoding="utf-8") as file:
        entry = json.loads(file.readline())

    assert entry["success"] is False
    assert entry["error"] == "not_allowed"
    assert "Путь запрещён" in entry["output"]