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

    agent_loop = isolated_project("agent_loop")
    permissions = isolated_project("permissions")

    fake = FakeBackend()
    monkeypatch.setattr(gui_module, "backend", fake)

    monkeypatch.setattr(agent_loop, "get_permission", lambda _: "confirm")
    permissions.set_confirmation_provider(permissions.deny_all)
    monkeypatch.setattr(agent_loop, "get_tool_implementation", lambda _: gui_module.click)

    result, decision = agent_loop._execute("click", {"x": 10, "y": 10})

    assert result["error"] == "denied"
    assert result["output"] == "Пользователь не разрешил выполнение действия."
    assert decision == "denied"
    assert fake.events == []


def test_audit_redacts_type_text(isolated_project):
    audit = isolated_project("audit")
    gui = isolated_project("capabilities.gui")

    gui_result = {"success": True, "data": {"typed_chars": 8}, "error": None, "metadata": {}}

    audit.record_tool_execution("type", {"text": "супер-секрет"}, gui_result, "confirmed")

    with open(audit.AUDIT_FILE, encoding="utf-8") as file:
        entry = json.loads(file.readline())

    assert entry["arguments"]["text"] == "***"
