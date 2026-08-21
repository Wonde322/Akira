import pytest


class FakeDialogue:
    DIALOGUE_TIMEOUT = 0.01
    WAKE_END_SILENCE_MS = 10


def _wire_voice_to_sink(engine, sink):
    engine.text_ready.connect(sink.append)


def _wake(engine, text, wake="акира", command=None):
    from desktop_app.voice import VoiceEngine
    dlg = FakeDialogue()
    dlg.record_utterance = lambda **kwargs: b"audio"
    dlg.transcribe = lambda audio: text
    dlg.find_wake_word = lambda value: wake if wake in value.lower() else None
    if command is None:
        command = text.replace("Акира", "").replace("акира", "").strip()
    dlg.remove_wake_word = lambda value, detected: command
    dlg.speak = lambda value: None
    engine._audio_ok = True
    engine._wake_listen(dlg)


def _dialogue(engine, text):
    dlg = FakeDialogue()
    dlg.record_utterance = lambda **kwargs: b"audio"
    dlg.transcribe = lambda audio: text
    engine._audio_ok = True
    engine._dialogue_listen(dlg)


def test_wake_command_reaches_worker_sink(qapp):
    from desktop_app.voice import VoiceEngine
    engine = VoiceEngine()
    received = []
    _wire_voice_to_sink(engine, received)
    _wake(engine, "Акира открой калькулятор")
    qapp.processEvents()
    assert received == ["открой калькулятор"]
    assert engine.is_dialogue() is True
    assert engine._listening is False


def test_wake_command_preserves_command_text(qapp):
    from desktop_app.voice import VoiceEngine
    engine = VoiceEngine()
    received = []
    _wire_voice_to_sink(engine, received)
    _wake(engine, "Акира включи музыку", command="включи музыку")
    qapp.processEvents()
    assert received == ["включи музыку"]


def test_non_wake_speech_never_reaches_worker(qapp):
    from desktop_app.voice import VoiceEngine
    engine = VoiceEngine()
    received = []
    _wire_voice_to_sink(engine, received)
    _wake(engine, "просто фоновая речь", wake="акира")
    qapp.processEvents()
    assert received == []
    assert engine.is_dialogue() is False


def test_bare_wake_enters_dialogue_without_worker_request(qapp):
    from desktop_app.voice import VoiceEngine
    engine = VoiceEngine()
    received = []
    _wire_voice_to_sink(engine, received)
    _wake(engine, "Акира", command="")
    qapp.processEvents()
    assert received == []
    assert engine.is_dialogue() is True
    assert engine._listening is True


def test_dialogue_followup_reaches_worker_without_second_wake(qapp):
    from desktop_app.voice import VoiceEngine
    engine = VoiceEngine()
    received = []
    _wire_voice_to_sink(engine, received)
    engine._set_dialogue(True)
    _dialogue(engine, "закрой Discord")
    qapp.processEvents()
    assert received == ["закрой Discord"]
    assert engine.is_dialogue() is True
    assert engine._listening is False


def test_dialogue_empty_transcript_never_reaches_worker(qapp):
    from desktop_app.voice import VoiceEngine
    engine = VoiceEngine()
    received = []
    _wire_voice_to_sink(engine, received)
    engine._set_dialogue(True)
    _dialogue(engine, "")
    qapp.processEvents()
    assert received == []
    assert engine.is_dialogue() is False


def test_capture_once_reaches_same_worker_sink(qapp):
    from desktop_app.voice import VoiceEngine
    engine = VoiceEngine(wake_enabled=False)
    received = []
    _wire_voice_to_sink(engine, received)
    dlg = FakeDialogue()
    dlg.record_utterance = lambda **kwargs: b"audio"
    dlg.transcribe = lambda audio: "текстовая команда"
    engine._capture(dlg)
    qapp.processEvents()
    assert received == ["текстовая команда"]
    assert engine._listening is False


def test_capture_empty_audio_does_not_submit(qapp):
    from desktop_app.voice import VoiceEngine
    engine = VoiceEngine(wake_enabled=False)
    received = []
    _wire_voice_to_sink(engine, received)
    dlg = FakeDialogue()
    dlg.record_utterance = lambda **kwargs: None
    engine._capture(dlg)
    qapp.processEvents()
    assert received == []


def test_capture_transcription_error_does_not_submit(qapp):
    from desktop_app.voice import VoiceEngine
    engine = VoiceEngine(wake_enabled=False)
    received = []
    _wire_voice_to_sink(engine, received)
    dlg = FakeDialogue()
    dlg.record_utterance = lambda **kwargs: b"audio"
    dlg.transcribe = lambda audio: (_ for _ in ()).throw(RuntimeError("boom"))
    engine._capture(dlg)
    qapp.processEvents()
    assert received == []


def test_end_turn_restores_wake_listening_after_command(qapp):
    from desktop_app.voice import VoiceEngine
    engine = VoiceEngine()
    _wake(engine, "Акира открой калькулятор")
    assert engine._listening is False
    engine._set_dialogue(False)
    engine._listening = True
    assert engine.is_dialogue() is False
    assert engine._listening is True


@pytest.mark.parametrize("answer", ["Готово.", "Не удалось выполнить действие.", ""], ids=["success", "friendly-error", "empty"])
def test_worker_answer_boundary_can_finish_voice_turn(qapp, answer):
    from desktop_app.voice import VoiceEngine
    engine = VoiceEngine()
    engine._set_dialogue(True)
    engine._listening = False
    # This mirrors the UI boundary: any terminal worker result must release
    # the voice turn rather than leaving the engine stuck in THINKING.
    engine._set_dialogue(False)
    engine._listening = True
    assert engine.is_dialogue() is False
    assert engine._listening is True


@pytest.mark.parametrize("message", ["one", "два", "три"], ids=["ascii", "cyrillic", "third"])
def test_worker_submit_boundary_accepts_normal_messages(qapp, message):
    from desktop_app.worker import BrainWorker
    worker = BrainWorker()
    worker.submit(message)
    assert worker._queue.get_nowait() == message
