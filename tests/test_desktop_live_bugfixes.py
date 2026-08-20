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


def test_typed_wake_does_not_enable_voice_dialogue():
    calls = []

    class Status:
        def setText(self, text):
            calls.append(("status", text))

        def setStyleSheet(self, text):
            pass

    class Input:
        def setEnabled(self, enabled):
            calls.append(("enabled", enabled))

        def setFocus(self):
            calls.append(("focus", None))

    class FakeWindow:
        status = Status()
        input = Input()

    ProactiveMainWindow._acknowledge_text_wake(FakeWindow())

    assert ("status", "Слушаю.") in calls
    assert ("enabled", True) in calls
    assert ("focus", None) in calls
