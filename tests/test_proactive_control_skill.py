import proactive_interruption_control as module
from skills.proactive_control import skill


def isolated(tmp_path, monkeypatch):
    control = module.ProactiveInterruptionControl(path=str(tmp_path / "mode.json"))
    monkeypatch.setattr(skill, "get_proactive_interruption_control", lambda: control)
    return control


def test_set_focus_mode(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    result = skill.set_proactive_mode("focus")
    assert result["success"] is True
    assert result["state"]["mode"] == "focus"


def test_set_timed_quiet_mode(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    result = skill.set_proactive_mode("quiet", 60)
    assert result["success"] is True
    assert result["state"]["mode"] == "quiet"
    assert result["state"]["quiet_until"] is not None


def test_invalid_mode_returns_error(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    result = skill.set_proactive_mode("chaos")
    assert result["success"] is False
    assert "mode" in result["error"]


def test_get_mode(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch).set_mode("focus")
    result = skill.get_proactive_mode()
    assert result == {"success": True, "state": {"mode": "focus", "quiet_until": None}}


def test_reset_mode(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch).set_mode("quiet")
    result = skill.reset_proactive_mode()
    assert result == {"success": True, "state": {"mode": "normal", "quiet_until": None}}


def test_tools_are_discoverable():
    names = {tool.name for tool in skill.TOOLS}
    assert names == {"set_proactive_mode", "get_proactive_mode", "reset_proactive_mode"}
