import builtins
import inspect
import json

from backend_fakes import FakeBackend


def _gui(isolated_project, monkeypatch):
    gui = isolated_project("capabilities.gui")
    fake = FakeBackend()
    monkeypatch.setattr(gui, "backend", fake)
    return gui, fake


def _registry(isolated_project):
    return isolated_project("tool_registry")


# ---------- Координаты и границы экрана ----------

def test_click_validates_coordinates(isolated_project, monkeypatch):
    gui, fake = _gui(isolated_project, monkeypatch)

    assert gui.click("a", 1)["error"] == "invalid_coordinate"
    assert gui.click(1, "b")["error"] == "invalid_coordinate"
    assert gui.click(1.5, 2.5)["success"] is True
    assert fake.events == [("click", 1, 2, "left", 1)]


def test_click_rejects_points_outside_screen(isolated_project, monkeypatch):
    gui, _ = _gui(isolated_project, monkeypatch)

    assert gui.click(1440, 100)["error"] == "out_of_bounds"
    assert gui.click(-1, 100)["error"] == "out_of_bounds"
    assert gui.click(100, 900)["error"] == "out_of_bounds"
    assert gui.click(100, -1)["error"] == "out_of_bounds"
    assert gui.click(1439, 899)["success"] is True
    assert gui.click(0, 0)["success"] is True


def test_click_rejects_invalid_button_and_clicks(isolated_project, monkeypatch):
    gui, fake = _gui(isolated_project, monkeypatch)

    assert gui.click(10, 10, button="back")["error"] == "invalid_button"
    assert gui.click(10, 10, clicks=0)["error"] == "invalid_clicks"
    assert gui.click(10, 10, clicks=11)["error"] == "invalid_clicks"
    assert gui.click(10, 10, clicks=2.5)["error"] == "invalid_clicks"
    assert fake.events == []

    assert gui.click(10, 10, button="right", clicks=2)["success"] is True
    assert fake.events == [("click", 10, 10, "right", 2)]


def test_click_returns_structured_result(isolated_project, monkeypatch):
    gui, _ = _gui(isolated_project, monkeypatch)

    result = gui.click(5, 7, button="middle")

    assert set(result.keys()) == {"success", "data", "error", "metadata"}
    assert result["data"] == {"x": 5, "y": 7, "button": "middle", "clicks": 1}


# ---------- select ----------

def test_select_is_composition_of_move_and_click(isolated_project, monkeypatch):
    gui, fake = _gui(isolated_project, monkeypatch)

    result = gui.select(30, 40)

    assert result["success"] is True
    assert result["data"]["action"] == "select"
    assert fake.events == [("move", 30, 40), ("click", 30, 40, "left", 1)]


def test_select_validates_coordinates(isolated_project, monkeypatch):
    gui, fake = _gui(isolated_project, monkeypatch)

    assert gui.select(1440, 10)["error"] == "out_of_bounds"
    assert gui.select("x", 1)["error"] == "invalid_coordinate"
    assert fake.events == []


# ---------- type ----------

def test_type_requires_text(isolated_project, monkeypatch):
    gui, fake = _gui(isolated_project, monkeypatch)

    assert gui.type_text("", target="Calculator")["error"] == "invalid_text"
    assert gui.type_text(42, target="Calculator")["error"] == "invalid_text"
    assert fake.events == []


def test_type_requires_target(isolated_project, monkeypatch):
    gui, fake = _gui(isolated_project, monkeypatch)

    result = gui.type_text("hello")

    assert result["success"] is False
    assert result["error"] == "target_required"
    assert fake.events == []


def test_type_handles_unicode(isolated_project, monkeypatch):
    gui, fake = _gui(isolated_project, monkeypatch)

    text = "héllo — привет, мир 世界"

    result = gui.type_text(text, target="Calculator")

    assert result["success"] is True
    assert result["data"]["typed_chars"] == len(text)
    assert result["data"]["target"] == "Calculator"
    assert fake.events == [("activate", "Calculator"), ("type", text)]


def test_type_activates_target_before_typing(isolated_project, monkeypatch):
    gui, fake = _gui(isolated_project, monkeypatch)

    result = gui.type_text("2+3=", target="Calculator")

    assert result["success"] is True
    assert fake.events == [("activate", "Calculator"), ("type", "2+3=")]
    assert fake.frontmost_app == "Calculator"


def test_type_target_not_frontmost_blocks_keystroke(isolated_project, monkeypatch):
    gui, fake = _gui(isolated_project, monkeypatch)

    class StuckBackend:
        def __init__(self):
            self.events = []

        def type_text(self, text):
            self.events.append(("type", text))

        def activate_app(self, app_name):
            self.events.append(("activate", app_name))

        def ui_metadata(self):
            return {"frontmost_app": "Terminal"}

    stuck = StuckBackend()
    monkeypatch.setattr(gui, "backend", stuck)

    result = gui.type_text("2+3=", target="Calculator")

    assert result["success"] is False
    assert result["error"] == "target_not_frontmost"
    assert stuck.events == [("activate", "Calculator")]
    assert "type" not in [event[0] for event in stuck.events]


def test_type_activation_failure_blocks_keystroke(isolated_project, monkeypatch):
    gui, fake = _gui(isolated_project, monkeypatch)

    class BrokenBackend:
        def __init__(self):
            self.events = []

        def type_text(self, text):
            self.events.append(("type", text))

        def activate_app(self, app_name):
            raise OSError("app not found")

        def ui_metadata(self):
            return None

    broken = BrokenBackend()
    monkeypatch.setattr(gui, "backend", broken)

    result = gui.type_text("2+3=", target="MissingApp")

    assert result["success"] is False
    assert result["error"] == "activate_failed"
    assert broken.events == []


def test_type_normalizes_app_names(isolated_project, monkeypatch):
    gui, fake = _gui(isolated_project, monkeypatch)

    result = gui.type_text("2+3=", target="/Applications/Calculator.app")

    assert result["success"] is True
    assert result["data"]["target"] == "Calculator"
    assert fake.events == [("activate", "Calculator"), ("type", "2+3=")]


def test_type_rejects_oversized_text(isolated_project, monkeypatch):
    from config import MAX_TYPE_LENGTH

    gui, fake = _gui(isolated_project, monkeypatch)

    result = gui.type_text("x" * (MAX_TYPE_LENGTH + 1), target="Calculator")

    assert result["error"] == "invalid_text"
    assert fake.events == []


def test_type_result_does_not_include_the_text(isolated_project, monkeypatch):
    gui, _ = _gui(isolated_project, monkeypatch)

    result = gui.type_text("пароль", target="Calculator")

    assert "пароль" not in json.dumps(result)


def test_prompt_on_stdin_is_strict_exact_match(isolated_project, monkeypatch):
    permissions = isolated_project("permissions")

    for polluted in ("2+3=да", "мусорда", "нет", "да\n мусор"):
        monkeypatch.setattr(
            builtins, "input", lambda _, value=polluted: value
        )
        assert permissions.prompt_on_stdin("open", {}) is False, polluted

    monkeypatch.setattr(builtins, "input", lambda _: "да")
    assert permissions.prompt_on_stdin("open", {}) is True


def test_gui_type_does_not_pollute_followup_confirmation(
    isolated_project, monkeypatch
):
    """GUI type в целевое приложение не пишет в stdin процесса.

    Раньше keystroke уходил в frontmost (Терминал, где Akira читает stdin):
    "2+3=" оседало в буфере, и следующий prompt читал "2+3=да" вместо "да" →
    подтверждение ложно отклонялось (permission denied).
    """
    import builtins
    import io
    import sys

    gui = isolated_project("capabilities.gui")
    permissions = isolated_project("permissions")

    fake = FakeBackend()
    monkeypatch.setattr(gui, "backend", fake)

    stdin_buffer = io.StringIO("да\n")
    monkeypatch.setattr(sys, "stdin", stdin_buffer)
    monkeypatch.setattr(
        builtins, "input", lambda prompt: stdin_buffer.readline().rstrip("\n")
    )

    result = gui.type_text("2+3=", target="Calculator")

    assert result["success"] is True
    assert fake.events == [("activate", "Calculator"), ("type", "2+3=")]

    assert permissions.prompt_on_stdin("open", {"target": "Calculator"}) is True


# ---------- key ----------

def test_key_allowlist_accepts_single_char_and_named(isolated_project, monkeypatch):
    key_mod = isolated_project("capabilities.key")
    fake = FakeBackend()
    monkeypatch.setattr(key_mod, "backend", fake)

    assert key_mod.key("a")["success"] is True
    assert key_mod.key("space")["success"] is True
    assert key_mod.key("escape")["success"] is True
    assert fake.events == [("key", [], "a"), ("key", [], "space"), ("key", [], "escape")]


def test_key_modifier_combinations_are_deduplicated(isolated_project, monkeypatch):
    key_mod = isolated_project("capabilities.key")
    fake = FakeBackend()
    monkeypatch.setattr(key_mod, "backend", fake)

    key_mod.key("command+cmd+shift+a")

    assert fake.events == [("key", ["command", "shift"], "a")]


def test_key_allowlist_rejects_unknown_tokens(isolated_project):
    key_mod = isolated_project("capabilities.key")

    assert key_mod.key("hyper+a")["error"] == "invalid_keys"
    assert key_mod.key("command+1234")["error"] == "invalid_keys"
    assert key_mod.key("fn")["error"] == "invalid_keys"


# ---------- scroll ----------

def test_scroll_limits(isolated_project, monkeypatch):
    gui, fake = _gui(isolated_project, monkeypatch)

    assert gui.scroll(amount=0)["error"] == "invalid_amount"
    assert gui.scroll(amount=51)["error"] == "invalid_amount"
    assert gui.scroll(amount=1.5)["error"] == "invalid_amount"
    assert gui.scroll(direction="diagonal")["error"] == "invalid_direction"
    assert fake.events == []


def test_scroll_all_directions_and_position(isolated_project, monkeypatch):
    gui, fake = _gui(isolated_project, monkeypatch)

    for direction in ("up", "down", "left", "right"):
        assert gui.scroll(direction=direction, amount=3)["success"] is True

    assert gui.scroll(x=100, y=200, direction="down")["success"] is True

    assert fake.events == [
        ("scroll", None, None, "up", 3),
        ("scroll", None, None, "down", 3),
        ("scroll", None, None, "left", 3),
        ("scroll", None, None, "right", 3),
        ("scroll", 100, 200, "down", 1),
    ]


def test_scroll_rejects_position_outside_screen(isolated_project, monkeypatch):
    gui, fake = _gui(isolated_project, monkeypatch)

    assert gui.scroll(x=2000, y=10)["error"] == "out_of_bounds"
    assert fake.events == []


# ---------- drag ----------

def test_drag_validates_coordinates(isolated_project, monkeypatch):
    gui, fake = _gui(isolated_project, monkeypatch)

    assert gui.drag(1, 2, 3, "x")["error"] == "invalid_coordinate"
    assert gui.drag(1, 2, 3, -4)["error"] == "out_of_bounds"
    assert gui.drag(2000, 2, 3, 4)["error"] == "out_of_bounds"
    assert fake.events == []


def test_drag_duration_limits(isolated_project, monkeypatch):
    gui, fake = _gui(isolated_project, monkeypatch)

    assert gui.drag(1, 1, 2, 2, duration=-1)["error"] == "invalid_duration"
    assert gui.drag(1, 1, 2, 2, duration=6)["error"] == "invalid_duration"
    assert gui.drag(1, 1, 2, 2, duration="fast")["error"] == "invalid_duration"
    assert fake.events == []

    assert gui.drag(1, 1, 2, 2, duration=0)["success"] is True
    assert gui.drag(1, 1, 2, 2, duration=0.5)["success"] is True


def test_drag_validates_button(isolated_project, monkeypatch):
    gui, fake = _gui(isolated_project, monkeypatch)

    assert gui.drag(1, 1, 2, 2, button="back")["error"] == "invalid_button"
    assert fake.events == []


def test_drag_executes_through_backend(isolated_project, monkeypatch):
    gui, fake = _gui(isolated_project, monkeypatch)

    result = gui.drag(10, 10, 200, 300, duration=0.5, button="right")

    assert result["success"] is True
    assert fake.events == [("drag", 10, 10, 200, 300, 0.5, "right")]


# ---------- Безопасность и permissions ----------

def test_gui_tools_are_confirm_by_default(isolated_project):
    registry = _registry(isolated_project)

    for name in ("click", "type", "select", "scroll", "drag", "key"):
        assert registry.get_default_tool_permissions()[name] == "confirm", name


def test_observe_remains_auto(isolated_project):
    registry = _registry(isolated_project)

    assert registry.get_default_tool_permissions()["observe"] == "auto"


def test_gui_action_blocked_by_permission_system(isolated_project, monkeypatch):
    import capabilities.gui as gui_module

    brain = isolated_project("brain")
    permissions = isolated_project("permissions")

    fake = FakeBackend()
    monkeypatch.setattr(gui_module, "backend", fake)

    monkeypatch.setattr(brain, "get_permission", lambda _: "confirm")
    permissions.set_confirmation_provider(permissions.deny_all)
    monkeypatch.setattr(brain, "get_tool_implementation", lambda _: gui_module.click)

    result = brain.execute_tool("click", {"x": 10, "y": 10})

    assert result == "Пользователь не разрешил выполнение действия."
    assert fake.events == []


def test_audit_redacts_type_text(isolated_project):
    audit = isolated_project("audit")
    gui = isolated_project("capabilities.gui")

    gui_result = {"success": True, "data": {"typed_chars": 8}, "error": None, "metadata": {}}

    audit.record_tool_execution("type", {"text": "супер-секрет"}, gui_result, "confirmed")

    with open(audit.AUDIT_FILE, encoding="utf-8") as file:
        entry = json.loads(file.readline())

    assert entry["arguments"]["text"] == "***"
    assert "супер-секрет" not in json.dumps(entry)


def test_other_tool_text_arguments_are_not_redacted(isolated_project):
    audit = isolated_project("audit")

    audit.record_tool_execution(
        "write",
        {"path": "/x", "content": "обычный текст"},
        {"success": True, "error": None, "output": "ok"},
        "auto",
    )

    with open(audit.AUDIT_FILE, encoding="utf-8") as file:
        entry = json.loads(file.readline())

    assert entry["arguments"]["content"] == "обычный текст"


# ---------- Registry и отсутствие app-specific hardcode ----------

def test_gui_tools_are_registered_with_capabilities_impl(isolated_project):
    registry = _registry(isolated_project)

    for name in ("click", "type", "select", "scroll", "drag"):
        tool = registry.get_tool_definition(name)

        assert tool is not None
        assert tool.implementation_module == "capabilities.gui"


def test_gui_schemas_match_signatures(isolated_project):
    registry = _registry(isolated_project)

    for name in ("click", "type", "select", "scroll", "drag"):
        tool = registry.get_tool_definition(name)
        parameters = inspect.signature(tool.implementation()).parameters

        for prop in tool.parameters["properties"]:
            assert prop in parameters, f"{name}: {prop}"

        for required in tool.parameters.get("required", []):
            assert parameters[required].default is inspect.Parameter.empty, name


def test_no_application_specific_hardcode_in_gui_layer():
    root = __import__("pathlib").Path(__file__).resolve().parents[1]

    banned = ("chrome", "spotify", "youtube", "figma", "safari", "photoshop", "calc")

    for module in ("gui.py", "backend.py", "key.py", "observe.py"):
        source = (root / "capabilities" / module).read_text(encoding="utf-8").lower()

        for word in banned:
            assert word not in source, f"{module}: упоминание '{word}'"