from __future__ import annotations

from types import SimpleNamespace


def test_voice_submit_keeps_microphone_paused_until_answer():
    from desktop_app.proactive_window import ProactiveMainWindow

    class FakeVoice:
        def __init__(self):
            self.resumes = 0
            self.stops = 0

        def resume(self):
            self.resumes += 1

        def stop_speaking(self):
            self.stops += 1

    class FakeWorker:
        def __init__(self):
            self.messages = []

        def submit(self, message):
            self.messages.append(message)

    window = ProactiveMainWindow.__new__(ProactiveMainWindow)
    window.voice = FakeVoice()
    window.worker = FakeWorker()
    window._state = "idle"
    window.SPEAKING = "speaking"
    window.input = SimpleNamespace(setEnabled=lambda enabled: None)
    window._last_voice = False
    window._append_message = lambda message, role: None
    window._set_state = lambda state: None

    window._submit("привет", voice=True)

    assert window.worker.messages == ["привет"]
    assert window._last_voice is True
    assert window.voice.resumes == 0


def test_wake_only_enters_normal_response_path():
    from desktop_app.voice import VoiceEngine

    class FakeDialogue:
        WAKE_TIMEOUT = 1
        WAKE_END_SILENCE_MS = 450

        def record_utterance(self, **kwargs):
            return object()

        def transcribe(self, audio):
            return "Акира"

        def find_wake_word(self, text):
            return "акира"

        def remove_wake_word(self, text, detected):
            return ""

    engine = VoiceEngine()
    engine._audio_ok = True
    emitted = []
    engine.text_ready.connect(emitted.append)

    engine._wake_listen(FakeDialogue())

    assert emitted == ["акира"]
    assert engine.is_dialogue() is True
    assert engine._listening is False
