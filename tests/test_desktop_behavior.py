from desktop_app.worker import _simple_greeting


def test_pure_greeting_is_short_and_does_not_reintroduce_akira():
    assert _simple_greeting("привет") == "Привет."
    assert _simple_greeting("Привет!") == "Привет."


def test_name_call_is_acknowledged_without_introduction():
    assert _simple_greeting("Акира") == "Да?"
    assert _simple_greeting("эй акира") == "Да?"


def test_compound_greeting_still_reaches_brain():
    assert _simple_greeting("привет, открой Spotify") is None
