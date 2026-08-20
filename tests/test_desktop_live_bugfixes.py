import pytest

from desktop_app.proactive_window import ProactiveMainWindow


@pytest.mark.parametrize(
    "text",
    [
        "Акира",
        "акира",
        "Акира!",
        "  Акира  ",
        "Акира...",
        "Akira",
        "akira",
        "AKIRA!",
        "... Акира?!",
    ],
)
def test_bare_wake_word_is_recognized(text):
    assert ProactiveMainWindow._is_wake_only(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "Акира открой калькулятор",
        "привет, Акира",
        "Акира123",
        "123Акира",
        "Акира_",
        "",
        "   ",
        None,
        "акиры",
        "akira please",
        "akira123",
        "video Akira",
    ],
)
def test_non_bare_text_is_not_treated_as_wake_word(text):
    assert ProactiveMainWindow._is_wake_only(text) is False


def test_typed_wake_does_not_enable_voice_dialogue(monkeypatch):
    window = object.__new__(ProactiveMainWindow)
    calls = []

    class Voice:
        def is_dialogue(self):
            return False

        def set_dialogue(self, enabled):
            calls.append(("dialogue", enabled))

        def resume(self):
            calls.append(("resume", None))

    window.voice = Voice()
    window.status = type("Status", (), {
        "setText": lambda self, text: calls.append(("status", text)),
        "setStyleSheet": lambda self, text: None,
    })()
    window.input = type("Input", (), {
        "setEnabled": lambda self, enabled: calls.append(("enabled", enabled)),
        "setFocus": lambda self: calls.append(("focus", None)),
    })()

    window._acknowledge_text_wake()

    assert ("dialogue", True) not in calls
    assert ("resume", None) not in calls
    assert ("status", "Слушаю.") in calls
