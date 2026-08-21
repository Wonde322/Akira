import queue

import pytest


class FakeDialogue:
    DIALOGUE_TIMEOUT = 0.01
    WAKE_END_SILENCE_MS = 10


def test_voice_initial_state(qapp):
    from desktop_app.voice import VoiceEngine
    engine = VoiceEngine()
    assert engine.is_dialogue() is False
    assert engine._listening is True
    assert engine._thread is None


def test_voice_stop_before_start_is_restart_safe(qapp):
    from desktop_app.voice import VoiceEngine
    engine = VoiceEngine()
    engine.stop()
    assert engine._stop_event.is_set()
    engine._stop_event.clear()
    assert engine._stop_event.is_set() is False


def test_voice_dialogue_state_is_idempotent(qapp):
    from desktop_app.voice import VoiceEngine
    engine = VoiceEngine()
    changes = []
    engine.dialogue_changed.connect(changes.append)
    engine._set_dialogue(True)
    engine._set_dialogue(True)
    engine._set_dialogue(False)
    engine._set_dialogue(False)
    qapp.processEvents()
    assert changes == [True, False]


def test_voice_safe_transcribe_success(qapp):
    from desktop_app.voice import VoiceEngine
    engine = VoiceEngine()
    dlg = FakeDialogue()
    dlg.transcribe = lambda audio: "открой калькулятор"
    assert engine._safe_transcribe(dlg, b"audio") == "открой калькулятор"


def test_voice_safe_transcribe_error_is_empty(qapp):
    from desktop_app.voice import VoiceEngine
    engine = VoiceEngine()
    dlg = FakeDialogue()
    dlg.transcribe = lambda audio: (_ for _ in ()).throw(RuntimeError("boom"))
    assert engine._safe_transcribe(dlg, b"audio") == ""


def test_voice_safe_transcribe_hallucination_is_empty(qapp, monkeypatch):
    import desktop_app.voice as voice
    engine = voice.VoiceEngine()
    dlg = FakeDialogue()
    dlg.transcribe = lambda audio: "шум"
    monkeypatch.setattr(voice, "_is_hallucination", lambda text: True)
    assert engine._safe_transcribe(dlg, b"audio") == ""


def test_voice_speak_restores_idle_after_success(qapp):
    from desktop_app.voice import VoiceEngine
    engine = VoiceEngine()
    states = []
    engine.state_changed.connect(states.append)
    dlg = FakeDialogue()
    dlg.speak = lambda text: None
    engine._listening = False
    engine._speak(dlg, "Да?")
    qapp.processEvents()
    assert engine._listening is True
    assert states[-2:] == [engine.SPEAKING, engine.IDLE]


def test_voice_speak_restores_idle_after_error(qapp):
    from desktop_app.voice import VoiceEngine
    engine = VoiceEngine()
    states = []
    engine.state_changed.connect(states.append)
    dlg = FakeDialogue()
    dlg.speak = lambda text: (_ for _ in ()).throw(RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        engine._speak(dlg, "Да?")
    qapp.processEvents()
    assert engine._listening is True
    assert states[-1] == engine.IDLE


def test_voice_capture_empty_returns_idle(qapp):
    from desktop_app.voice import VoiceEngine
    engine = VoiceEngine(wake_enabled=False)
    states = []
    engine.state_changed.connect(states.append)
    dlg = FakeDialogue()
    dlg.record_utterance = lambda **kwargs: None
    engine._capture(dlg)
    qapp.processEvents()
    assert states[-1] == engine.IDLE


def test_voice_capture_emits_text_and_thinking(qapp):
    from desktop_app.voice import VoiceEngine
    engine = VoiceEngine(wake_enabled=False)
    texts, states = [], []
    engine.text_ready.connect(texts.append)
    engine.state_changed.connect(states.append)
    dlg = FakeDialogue()
    dlg.record_utterance = lambda **kwargs: b"audio"
    dlg.transcribe = lambda audio: "тест"
    engine._capture(dlg)
    qapp.processEvents()
    assert texts == ["тест"]
    assert states[-1] == engine.THINKING
    assert engine._listening is False


def test_dialogue_timeout_returns_idle_and_disables_dialogue(qapp):
    from desktop_app.voice import VoiceEngine
    engine = VoiceEngine()
    engine._set_dialogue(True)
    states = []
    engine.state_changed.connect(states.append)
    dlg = FakeDialogue()
    dlg.record_utterance = lambda **kwargs: None
    engine._audio_ok = True
    engine._dialogue_listen(dlg)
    qapp.processEvents()
    assert engine.is_dialogue() is False
    assert states[-1] == engine.IDLE


def test_dialogue_empty_transcription_returns_idle(qapp):
    from desktop_app.voice import VoiceEngine
    engine = VoiceEngine()
    engine._set_dialogue(True)
    dlg = FakeDialogue()
    dlg.record_utterance = lambda **kwargs: b"audio"
    dlg.transcribe = lambda audio: ""
    engine._audio_ok = True
    engine._dialogue_listen(dlg)
    assert engine.is_dialogue() is False


def test_dialogue_without_audio_does_not_transcribe(qapp):
    from desktop_app.voice import VoiceEngine
    engine = VoiceEngine()
    called = []
    dlg = FakeDialogue()
    dlg.record_utterance = lambda **kwargs: called.append(True)
    engine._audio_ok = False
    engine._dialogue_listen(dlg)
    assert called == []


def test_wake_without_audio_does_not_record(qapp):
    from desktop_app.voice import VoiceEngine
    engine = VoiceEngine()
    called = []
    dlg = FakeDialogue()
    dlg.record_utterance = lambda **kwargs: called.append(True)
    engine._audio_ok = False
    engine._wake_listen(dlg)
    assert called == []


def test_wake_non_match_keeps_dialogue_off(qapp):
    from desktop_app.voice import VoiceEngine
    engine = VoiceEngine()
    dlg = FakeDialogue()
    dlg.record_utterance = lambda **kwargs: b"audio"
    dlg.transcribe = lambda audio: "обычная речь"
    dlg.find_wake_word = lambda text: None
    engine._audio_ok = True
    engine._wake_listen(dlg)
    assert engine.is_dialogue() is False


def test_wake_bare_name_enters_dialogue_and_speaks(qapp):
    from desktop_app.voice import VoiceEngine
    engine = VoiceEngine()
    spoken = []
    dlg = FakeDialogue()
    dlg.record_utterance = lambda **kwargs: b"audio"
    dlg.transcribe = lambda audio: "Акира"
    dlg.find_wake_word = lambda text: "акира"
    dlg.remove_wake_word = lambda text, wake: ""
    dlg.speak = spoken.append
    engine._audio_ok = True
    engine._wake_listen(dlg)
    assert engine.is_dialogue() is True
    assert spoken == ["Да?"]


def test_wake_command_emits_text_and_thinking(qapp):
    from desktop_app.voice import VoiceEngine
    engine = VoiceEngine()
    texts = []
    engine.text_ready.connect(texts.append)
    dlg = FakeDialogue()
    dlg.record_utterance = lambda **kwargs: b"audio"
    dlg.transcribe = lambda audio: "Акира открой Discord"
    dlg.find_wake_word = lambda text: "акира"
    dlg.remove_wake_word = lambda text, wake: "открой Discord"
    engine._audio_ok = True
    engine._wake_listen(dlg)
    qapp.processEvents()
    assert texts == ["открой Discord"]
    assert engine.is_dialogue() is True
    assert engine._listening is False


def test_worker_prepare_start_discards_only_shutdown_sentinels(qapp):
    from desktop_app.worker import BrainWorker
    worker = BrainWorker()
    worker._queue.put("one")
    worker._queue.put(None)
    worker._queue.put("two")
    worker._stop = True
    worker._prepare_start()
    assert worker._stop is False
    assert worker._queue.get_nowait() == "one"
    assert worker._queue.get_nowait() == "two"
    with pytest.raises(queue.Empty):
        worker._queue.get_nowait()


def test_worker_prepare_start_is_idempotent(qapp):
    from desktop_app.worker import BrainWorker
    worker = BrainWorker()
    worker.submit("message")
    worker._prepare_start()
    worker._prepare_start()
    assert worker._queue.get_nowait() == "message"


def test_worker_submit_none_is_ignored(qapp):
    from desktop_app.worker import BrainWorker
    worker = BrainWorker()
    worker.submit(None)
    with pytest.raises(queue.Empty):
        worker._queue.get_nowait()


def test_worker_request_stop_sets_flag_and_sentinel(qapp):
    from desktop_app.worker import BrainWorker
    worker = BrainWorker()
    worker.request_stop()
    assert worker._stop is True
    assert worker._queue.get_nowait() is None


def test_worker_prepare_start_after_stop_clears_shutdown(qapp):
    from desktop_app.worker import BrainWorker
    worker = BrainWorker()
    worker.request_stop()
    worker._prepare_start()
    assert worker._stop is False
    with pytest.raises(queue.Empty):
        worker._queue.get_nowait()


def test_worker_friendly_error_api_key(qapp):
    from desktop_app.worker import _friendly_error
    assert "GROQ_API_KEY" in _friendly_error(RuntimeError("api_key missing"))


def test_worker_friendly_error_denied(qapp):
    from desktop_app.worker import _friendly_error
    assert _friendly_error(RuntimeError("permission denied")) == "Действие не разрешено."


def test_worker_friendly_error_generic(qapp):
    from desktop_app.worker import _friendly_error
    assert "Не удалось" in _friendly_error(RuntimeError("boom"))
