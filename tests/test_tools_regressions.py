import subprocess

import tools


def test_set_volume_rejects_invalid_value(monkeypatch):
    monkeypatch.setattr(tools, "_run_osascript", lambda script: (_ for _ in ()).throw(AssertionError("must not run")))
    assert tools.set_volume("loud") == "Уровень громкости должен быть числом от 0 до 100."


def test_set_volume_does_not_record_failed_command(monkeypatch):
    called = []
    monkeypatch.setattr(tools, "_run_osascript", lambda script: subprocess.CompletedProcess([], 1, "", "error"))
    monkeypatch.setattr(tools, "add_event", lambda message: called.append(message))

    assert tools.set_volume(50) == "Не удалось установить громкость."
    assert called == []


def test_get_volume_reports_command_failure(monkeypatch):
    monkeypatch.setattr(tools, "_run_osascript", lambda script: subprocess.CompletedProcess([], 1, "", "error"))
    assert tools.get_volume() == "Не удалось получить текущую громкость."
