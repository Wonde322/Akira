import pytest

from voice.dialogue import find_wake_word


@pytest.mark.parametrize("text", [
    "Акира",
    "акира, открой калькулятор",
    "... Акира?!",
    "Кира включи музыку",
    "Акера что на экране",
    "Акиро",
])
def test_standalone_wake_tokens_are_detected(text):
    assert find_wake_word(text) is not None


@pytest.mark.parametrize("text", [
    "Акира123",
    "123Акира",
    "акира_test",
    "videoAkira",
    "акира123 открой дискорд",
    None,
])
def test_embedded_or_non_text_wake_tokens_are_rejected(text):
    assert find_wake_word(text) is None
