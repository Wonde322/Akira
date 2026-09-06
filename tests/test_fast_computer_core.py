from __future__ import annotations

import computer_state
import fast_commands


def test_application_resolver_understands_russian_colloquialisms_without_alias_table():
    resolver = computer_state.ApplicationResolver()
    resolver._cache = [
        computer_state.Application("Spotify", "/Applications/Spotify.app", "com.spotify.client"),
        computer_state.Application("Telegram", "/Applications/Telegram.app", "org.telegram.desktop"),
        computer_state.Application("Google Chrome", "/Applications/Google Chrome.app", "com.google.Chrome"),
    ]

    assert resolver.resolve("спотик").name == "Spotify"
    assert resolver.resolve("тг").name == "Telegram"
    assert resolver.resolve("хром").name == "Google Chrome"


def test_fast_open_does_not_enter_llm(monkeypatch):
    monkeypatch.setattr(fast_commands, "open_target", lambda target: {
        "success": True,
        "data": {"application": "Spotify"},
    })
    result = fast_commands.handle("открой спотик")
    assert result["handled"] is True
    assert result["action"] == "open"
    assert result["response"] == "Открыл Spotify."


def test_fast_open_accepts_wake_prefix(monkeypatch):
    monkeypatch.setattr(fast_commands, "open_target", lambda target: {
        "success": True,
        "data": {"application": "Spotify"},
    })
    result = fast_commands.handle("Акира, открой спотик")
    assert result["response"] == "Открыл Spotify."


def test_fast_close_does_not_use_shell(monkeypatch):
    monkeypatch.setattr(fast_commands, "close_target", lambda target: {
        "success": True,
        "data": {"application": "Spotify", "closed": True},
    })
    result = fast_commands.handle("закрой спотик")
    assert result["handled"] is True
    assert result["action"] == "close"
    assert result["response"] == "Закрыл Spotify."


def test_fast_volume_queries_use_authoritative_state(monkeypatch):
    monkeypatch.setattr(fast_commands, "volume", lambda: {"level": 37, "muted": False})
    result = fast_commands.handle("какая громкость")
    assert result["response"] == "Громкость: 37%."


def test_fast_frontmost_query(monkeypatch):
    monkeypatch.setattr(fast_commands, "frontmost_app", lambda: {"name": "Spotify", "path": "/Applications/Spotify.app"})
    result = fast_commands.handle("какое приложение сейчас активно")
    assert result["response"] == "Сейчас активно: Spotify."
