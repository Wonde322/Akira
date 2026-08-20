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


def test_typed_wake_cancels_stale_voice_dialogue_and_keeps_text_input():
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

    class Voice:
        def set_dialogue(self, enabled):
            calls.append(("dialogue", enabled))

        def resume(self):
            calls.append(("resume", None))

    class FakeWindow:
        IDLE = "idle"
        status = Status()
        input = Input()
        voice = Voice()

        def _set_state(self, state):
            calls.append(("state", state))

    ProactiveMainWindow._acknowledge_text_wake(FakeWindow())

    assert ("dialogue", False) in calls
    assert ("resume", None) in calls
    assert ("state", "idle") in calls
    assert ("status", "Слушаю.") in calls
    assert ("enabled", True) in calls
    assert ("focus", None) in calls


def test_voice_dialogue_timeout_returns_to_idle_and_disables_dialogue():
    from desktop_app.voice import VoiceEngine

    events = []

    class Signal:
        def emit(self, value):
            events.append(value)

    class FakeEngine:
        LISTENING = VoiceEngine.LISTENING
        IDLE = VoiceEngine.IDLE
        _audio_ok = True
        _interrupt = None
        _dialogue = True
        dialogue_changed = Signal()

        def _emit_state(self, state):
            events.append(("state", state))

        def _set_dialogue(self, enabled):
            self._dialogue = bool(enabled)
            self.dialogue_changed.emit(self._dialogue)

    class FakeDialogue:
        DIALOGUE_TIMEOUT = 1

        @staticmethod
        def record_utterance(**kwargs):
            return None

    engine = FakeEngine()
    ProactiveMainWindow  # keep import regression coverage explicit
    VoiceEngine._dialogue_listen(engine, FakeDialogue())

    assert engine._dialogue is False
    assert False in events
    assert ("state", VoiceEngine.IDLE) in events
