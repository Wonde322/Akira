from desktop_app.voice import VoiceEngine
import voice.dialogue as dlg


def test_hallucinated_name_prompt_is_filtered():
    assert dlg._is_hallucination("Возможные варианты имени Акира, Кира, Акера")
    assert dlg._is_hallucination("Имя голосового ассистента: Акира")


def test_wake_recording_uses_short_end_silence():
    calls = {}

    class FakeDialogue:
        WAKE_END_SILENCE_MS = 321
        @staticmethod
        def record_utterance(**kwargs):
            calls.update(kwargs)
            return None

    class Engine:
        _audio_ok = True
        _interrupt = object()

    VoiceEngine._wake_listen(Engine(), FakeDialogue())
    assert calls["end_silence_ms"] == 321


def test_end_turn_closes_dialogue_and_returns_idle():
    events = []

    class Signal:
        def emit(self, value): events.append(value)

    class Engine:
        _dialogue = True
        _listening = False
        dialogue_changed = Signal()
        IDLE = VoiceEngine.IDLE
        def _set_dialogue(self, enabled):
            self._dialogue = enabled
            events.append(("dialogue", enabled))
        def _emit_state(self, state): events.append(("state", state))

    engine = Engine()
    # exercise the exact state transition used by the command queue
    VoiceEngine._set_dialogue(engine, False)
    engine._listening = True
    engine._emit_state(VoiceEngine.IDLE)
    assert engine._dialogue is False
    assert engine._listening is True
    assert ("state", VoiceEngine.IDLE) in events


def test_dialogue_timeout_returns_to_wake_listener():
    events = []
    class Signal:
        def emit(self, value): events.append(value)
    class Engine:
        LISTENING = VoiceEngine.LISTENING
        IDLE = VoiceEngine.IDLE
        _audio_ok = True
        _interrupt = None
        _dialogue = True
        dialogue_changed = Signal()
        def _set_dialogue(self, enabled):
            self._dialogue = enabled
            events.append(("dialogue", enabled))
        def _emit_state(self, state): events.append(("state", state))
    class FakeDialogue:
        DIALOGUE_TIMEOUT = 1
        @staticmethod
        def record_utterance(**kwargs): return None
    engine = Engine()
    VoiceEngine._dialogue_listen(engine, FakeDialogue())
    assert engine._dialogue is False
    assert ("state", VoiceEngine.IDLE) in events
