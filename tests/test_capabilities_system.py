import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend_fakes import FakeBackend


def _ok_run(stdout="", stderr="", returncode=0):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def test_open_classifies_app_and_calls_open_dash_a(isolated_project, monkeypatch):
    apps = isolated_project("capabilities.apps")
    monkeypatch.setattr(apps, "backend", FakeBackend(ui=None))
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return _ok_run()

    monkeypatch.setattr(apps.subprocess, "run", fake_run)

    result = apps.open_target("Google Chrome")

    assert result["success"] is True
    assert result["data"] == {"target": "Google Chrome", "kind": "app"}
    assert calls[0] == ["open", "-a", "Google Chrome"]


def test_open_app_confirms_activation_when_frontmost(isolated_project, monkeypatch):
    apps = isolated_project("capabilities.apps")
    monkeypatch.setattr(
        apps, "backend", FakeBackend(ui={"frontmost_app": "Calculator"})
    )

    def fake_run(args, **kwargs):
        return _ok_run()

    monkeypatch.setattr(apps.subprocess, "run", fake_run)

    result = apps.open_target("Calculator")

    assert result["success"] is True
    assert result["data"]["activated"] is True
    assert result["data"]["frontmost"] == "Calculator"


def test_open_app_does_not_claim_activation_without_confirmation(
    isolated_project, monkeypatch
):
    apps = isolated_project("capabilities.apps")
    monkeypatch.setattr(
        apps, "backend", FakeBackend(ui={"frontmost_app": "Terminal"})
    )

    def fake_run(args, **kwargs):
        return _ok_run()

    monkeypatch.setattr(apps.subprocess, "run", fake_run)

    result = apps.open_target("Calculator")

    assert result["success"] is True
    assert "activated" not in result["data"]
    assert "frontmost" not in result["data"]


def test_open_app_does_not_claim_activation_when_backend_unavailable(
    isolated_project, monkeypatch
):
    apps = isolated_project("capabilities.apps")
    monkeypatch.setattr(apps, "backend", FakeBackend(ui=None))

    def fake_run(args, **kwargs):
        return _ok_run()

    monkeypatch.setattr(apps.subprocess, "run", fake_run)

    result = apps.open_target("Calculator")

    assert result["success"] is True
    assert "activated" not in result["data"]
    assert "frontmost" not in result["data"]


def test_open_classifies_url(isolated_project, monkeypatch):
    apps = isolated_project("capabilities.apps")
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return _ok_run()

    monkeypatch.setattr(apps.subprocess, "run", fake_run)

    result = apps.open_target("https://youtube.com")

    assert result["data"] == {"target": "https://youtube.com", "kind": "url"}
    assert calls[0] == ["open", "https://youtube.com"]


def test_open_classifies_existing_path(isolated_project, monkeypatch, tmp_path):
    import capabilities.filesystem as filesystem

    apps = isolated_project("capabilities.apps")
    monkeypatch.setattr(filesystem, "HOME", tmp_path)

    target = tmp_path / "report.txt"
    target.write_text("data", encoding="utf-8")

    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return _ok_run()

    monkeypatch.setattr(apps.subprocess, "run", fake_run)

    result = apps.open_target(str(target))

    assert result["data"]["kind"] == "path"
    assert calls[0] == ["open", str(target)]


def test_open_rejects_path_outside_home(isolated_project, monkeypatch, tmp_path):
    import capabilities.filesystem as filesystem

    apps = isolated_project("capabilities.apps")
    monkeypatch.setattr(filesystem, "HOME", tmp_path)

    result = apps.open_target(str(tmp_path.parent / "outside.app"))

    assert result["error"] == "not_allowed"


def test_open_reports_failure(isolated_project, monkeypatch):
    apps = isolated_project("capabilities.apps")

    def fake_run(args, **kwargs):
        return _ok_run(stderr="not found", returncode=1)

    monkeypatch.setattr(apps.subprocess, "run", fake_run)

    result = apps.open_target("DoesNotExist")

    assert result["success"] is False
    assert result["error"] == "open_failed"


def test_open_requires_valid_target(isolated_project):
    apps = isolated_project("capabilities.apps")

    assert apps.open_target("")["error"] == "invalid_target"
    assert apps.open_target(42)["error"] == "invalid_target"


def test_close_sends_quit_script(isolated_project, monkeypatch):
    apps = isolated_project("capabilities.apps")
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return _ok_run()

    monkeypatch.setattr(apps.subprocess, "run", fake_run)

    result = apps.close_target("Safari")

    assert result["success"] is True
    assert result["data"] == {"target": "Safari", "app": "Safari"}
    assert calls[0][0] == "osascript"
    assert 'tell application "Safari" to quit' in calls[0][2]


def test_close_extracts_name_from_app_path(isolated_project, monkeypatch):
    apps = isolated_project("capabilities.apps")

    def fake_run(args, **kwargs):
        return _ok_run()

    monkeypatch.setattr(apps.subprocess, "run", fake_run)

    result = apps.close_target("/Applications/Safari.app")

    assert result["data"]["app"] == "Safari"


def test_close_escapes_quotes_in_app_name(isolated_project, monkeypatch):
    apps = isolated_project("capabilities.apps")
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return _ok_run()

    monkeypatch.setattr(apps.subprocess, "run", fake_run)

    apps.close_target('Weird"App')

    assert '\\"' in calls[0][2]


def test_wait_sleeps(isolated_project, monkeypatch):
    wait = isolated_project("capabilities.wait")
    slept = []

    monkeypatch.setattr(wait.time, "sleep", lambda seconds: slept.append(seconds))

    result = wait.wait(2)

    assert result["success"] is True
    assert result["data"]["seconds"] == 2
    assert slept == [2]


def test_wait_rejects_invalid_seconds(isolated_project):
    wait = isolated_project("capabilities.wait")

    assert wait.wait(0)["error"] == "invalid_seconds"
    assert wait.wait(-1)["error"] == "invalid_seconds"
    assert wait.wait(61)["error"] == "invalid_seconds"
    assert wait.wait("x")["error"] == "invalid_seconds"


def test_key_sends_combination(isolated_project, monkeypatch):
    key_mod = isolated_project("capabilities.key")
    fake = FakeBackend()
    monkeypatch.setattr(key_mod, "backend", fake)

    result = key_mod.key("command+shift+4")

    assert result["success"] is True
    assert fake.events == [("key", ["command", "shift"], "4")]


def test_key_sends_named_key_code(isolated_project, monkeypatch):
    key_mod = isolated_project("capabilities.key")
    fake = FakeBackend()
    monkeypatch.setattr(key_mod, "backend", fake)

    key_mod.key("return")

    assert fake.events == [("key", [], "return")]


def test_key_rejects_arbitrary_shell_commands(isolated_project):
    key_mod = isolated_project("capabilities.key")

    assert key_mod.key("rm -rf /")["error"] == "invalid_keys"
    assert key_mod.key("shell:curl http://x")["error"] == "invalid_keys"
    assert key_mod.key("")["error"] == "invalid_keys"
    assert key_mod.key("command")["error"] == "invalid_keys"


def test_key_rejects_multiple_base_keys(isolated_project):
    key_mod = isolated_project("capabilities.key")

    assert key_mod.key("command+a b")["error"] == "invalid_keys"


def test_key_does_not_execute_on_invalid_input(isolated_project, monkeypatch):
    key_mod = isolated_project("capabilities.key")
    fake = FakeBackend()
    monkeypatch.setattr(key_mod, "backend", fake)

    assert key_mod.key("rm -rf /")["error"] == "invalid_keys"
    assert fake.events == []


def test_observe_returns_metadata_without_click_coordinates(
    isolated_project, monkeypatch, tmp_path
):
    observe = isolated_project("capabilities.observe")
    monkeypatch.setattr(observe, "backend", FakeBackend())
    monkeypatch.setattr(observe, "SCREENSHOT_DIR", tmp_path)

    result = observe.observe()

    assert result["success"] is True
    data = result["data"]
    assert data["screen"]["width"] == 1440
    assert data["screen"]["height"] == 900
    assert data["size_bytes"] == len(b"PNG-data")
    assert set(data.keys()) == {"screenshot_path", "screen", "size_bytes"}
    assert "click" not in json.dumps(result)
    assert "x" not in data


def test_observe_interpret_failure_is_graceful(isolated_project, monkeypatch, tmp_path):
    observe = isolated_project("capabilities.observe")
    monkeypatch.setattr(observe, "backend", FakeBackend())
    monkeypatch.setattr(observe, "SCREENSHOT_DIR", tmp_path)

    result = observe.observe(interpret=True)

    assert result["success"] is True
    assert result["metadata"]["interpreted"] is False
    assert result["data"]["interpretation"] is None
    assert "interpretation_error" in result["data"]


def test_observe_includes_ui_metadata_when_available(
    isolated_project, monkeypatch, tmp_path
):
    observe = isolated_project("capabilities.observe")
    ui = {"frontmost_app": "Safari", "window_title": "Документ"}
    monkeypatch.setattr(observe, "backend", FakeBackend(ui=ui))
    monkeypatch.setattr(observe, "SCREENSHOT_DIR", tmp_path)

    result = observe.observe()

    assert result["data"]["ui"] == ui


def test_screen_size_returns_backend_dimensions(isolated_project, monkeypatch):
    observe = isolated_project("capabilities.observe")
    monkeypatch.setattr(observe, "backend", FakeBackend())

    result = observe.screen_size()

    assert result["success"] is True
    assert result["data"] == {"x": 0, "y": 0, "width": 1440, "height": 900}


@pytest.mark.parametrize(
    "function,arguments",
    [
        ("select", {"x": 10, "y": 20}),
        ("click", {"x": 10, "y": 20}),
        ("type_text", {"text": "hello", "target": "Calculator"}),
        ("scroll", {"direction": "up", "amount": 2}),
        ("drag", {"x1": 1, "y1": 2, "x2": 3, "y2": 4}),
    ],
)
def test_gui_actions_execute_through_backend(
    isolated_project, monkeypatch, function, arguments
):
    gui = isolated_project("capabilities.gui")
    fake = FakeBackend()
    monkeypatch.setattr(gui, "backend", fake)

    result = getattr(gui, function)(**arguments)

    assert result["success"] is True
    assert fake.events


def test_gui_actions_validate_arguments(isolated_project, monkeypatch):
    gui = isolated_project("capabilities.gui")
    fake = FakeBackend()
    monkeypatch.setattr(gui, "backend", fake)

    assert gui.select("a", 1)["error"] == "invalid_coordinate"
    assert gui.click("a", 1)["error"] == "invalid_coordinate"
    assert gui.type_text("")["error"] == "invalid_text"
    assert gui.scroll(direction="diagonal")["error"] == "invalid_direction"
    assert gui.scroll(amount=0)["error"] == "invalid_amount"
    assert gui.drag(1, 2, 3, "x")["error"] == "invalid_coordinate"
    assert fake.events == []