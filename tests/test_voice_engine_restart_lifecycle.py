import queue


def _install_fake_thread(monkeypatch):
    import desktop_app.voice as voice

    created = []

    class FakeThread:
        def __init__(self, target, daemon, name):
            self.target = target
            self.daemon = daemon
            self.name = name
            self.started = False
            self.alive = False
            self.joined = False

        def start(self):
            self.started = True
            self.alive = True

        def is_alive(self):
            return self.alive

        def join(self, timeout=None):
            self.joined = True
            self.alive = False

    def factory(*args, **kwargs):
        thread = FakeThread(*args, **kwargs)
        created.append(thread)
        return thread

    monkeypatch.setattr(voice.threading, "Thread", factory)
    return created


def test_stop_before_start_does_not_poison_next_start(monkeypatch):
    from desktop_app.voice import VoiceEngine

    created = _install_fake_thread(monkeypatch)
    engine = VoiceEngine()
    engine.stop()
    assert engine._stop_event.is_set()

    engine.start()

    assert len(created) == 1
    assert created[0].started is True
    assert engine._stop_event.is_set() is False


def test_stop_clears_dead_thread_reference(monkeypatch):
    from desktop_app.voice import VoiceEngine

    created = _install_fake_thread(monkeypatch)
    engine = VoiceEngine()
    engine.start()
    engine.stop()

    assert created[0].joined is True
    assert engine._thread is None


def test_start_after_stop_creates_fresh_worker(monkeypatch):
    from desktop_app.voice import VoiceEngine

    created = _install_fake_thread(monkeypatch)
    engine = VoiceEngine()
    engine.start()
    engine.stop()
    engine.start()

    assert len(created) == 2
    assert created[1].started is True


def test_repeated_start_while_alive_does_not_duplicate_worker(monkeypatch):
    from desktop_app.voice import VoiceEngine

    created = _install_fake_thread(monkeypatch)
    engine = VoiceEngine()
    engine.start()
    engine.start()

    assert len(created) == 1


def test_restart_discards_stale_stop_command(monkeypatch):
    from desktop_app.voice import VoiceEngine

    _install_fake_thread(monkeypatch)
    engine = VoiceEngine()
    engine._commands.put(("stop", None))
    old_queue = engine._commands
    engine.start()

    assert engine._commands is not old_queue
    assert engine._commands.empty()


def test_restart_resets_interrupt_and_cancel_events(monkeypatch):
    from desktop_app.voice import VoiceEngine

    _install_fake_thread(monkeypatch)
    engine = VoiceEngine()
    engine._interrupt.set()
    engine._cancel_event.set()
    engine._stop_event.set()

    engine.start()

    assert engine._interrupt.is_set() is False
    assert engine._cancel_event.is_set() is False
    assert engine._stop_event.is_set() is False


def test_stop_leaves_voice_in_non_dialogue_state(monkeypatch):
    from desktop_app.voice import VoiceEngine

    _install_fake_thread(monkeypatch)
    engine = VoiceEngine()
    engine._set_dialogue(True)

    engine.stop()

    assert engine.is_dialogue() is False


def test_stop_resets_audio_flag(monkeypatch):
    from desktop_app.voice import VoiceEngine

    _install_fake_thread(monkeypatch)
    engine = VoiceEngine()
    engine._audio_ok = True

    engine.stop()

    assert engine._audio_ok is False
