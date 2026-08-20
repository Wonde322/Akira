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
        "",
        "   ",
        None,
        "акиры",
        "akira please",
    ],
)
def test_non_bare_text_is_not_treated_as_wake_word(text):
    assert ProactiveMainWindow._is_wake_only(text) is False
