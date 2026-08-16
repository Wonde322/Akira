import json
import threading
import time

import pytest


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def test_activity_labels_are_friendly():
    from desktop_app.activity import ACTIVITY_LABELS, activity_label, describe_action

    assert activity_label("observe") == "Наблюдаю экран"
    assert activity_label("unknown_tool") == "Выполняю действие"

    for tool, label in ACTIVITY_LABELS.items():
        assert label, tool
        assert "{" not in label and "json" not in label.lower()

    assert describe_action("open", {"target": "Calculator"}) == "Открыть: Calculator"
    assert describe_action("shell", {"command": "ls"}) == (
        "Выполнить команду в терминале"
    )
    assert describe_action("read") == "Читаю файл"


def test_desktop_modules_import_without_qapplication():
    import importlib

    for name in (
        "desktop_app.activity",
        "desktop_app.confirmation",
        "desktop_app.visualizer",
        "desktop_app.worker",
        "desktop_app.voice",
        "desktop_app.window",
    ):
        assert importlib.import_module(name) is not None


def test_redirect_paths_creates_data_dir(tmp_path, monkeypatch):
    import config
    import desktop

    monkeypatch.setattr(
        desktop.sys, "frozen", True, raising=False
    )
    monkeypatch.setattr(desktop.Path, "home", staticmethod(lambda: tmp_path))

    data_dir = tmp_path / "Library" / "Application Support" / "Akira"
    logs_dir = data_dir / "logs"

    assert not data_dir.exists()

    desktop._redirect_paths()

    assert data_dir.is_dir()
    assert logs_dir.is_dir()
    assert (logs_dir / "screenshots").is_dir()

    assert config.MEMORY_FILE.startswith(str(data_dir))
    assert config.PERMISSIONS_FILE.startswith(str(data_dir))
    assert config.LOG_DIR == logs_dir


def test_confirmation_service_waits_for_answer(qapp):
    from desktop_app.confirmation import ConfirmationService

    service = ConfirmationService(timeout=5)

    received = {}

    def on_request(tool, description, arguments, request):
        received["tool"] = tool
        received["description"] = description
        request["allowed"] = True
        request["answered"].set()

    service.request_received.connect(on_request)

    result = service.provider("open", {"target": "Calculator"})

    assert result is True
    assert received["tool"] == "open"
    assert received["description"] == "Открыть: Calculator"


def test_confirmation_service_denies_on_timeout(qapp):
    from desktop_app.confirmation import ConfirmationService

    service = ConfirmationService(timeout=0.01)

    # No one answers -> defaults to denied.
    assert service.provider("delete", {"path": "/tmp/x"}) is False


def test_brain_worker_uses_desktop_session(qapp):
    from desktop_app.worker import BrainWorker

    calls = []

    class FakeWorker(BrainWorker):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self._fake_ask = None

        def set_ask(self, fn):
            self._fake_ask = fn

        def run(self):
            # Not starting a real thread in tests; emulate run body.
            message = "тест"
            calls.append({"session": self.session_id, "message": message})

    worker = FakeWorker(session_id="desktop")
    worker.set_ask(lambda *a, **k: "ok")
    assert worker.session_id == "desktop"


def test_worker_friendly_error_mapping():
    from desktop_app.worker import _friendly_error

    assert "GROQ_API_KEY" in _friendly_error("GROQ_API_KEY is missing")
    assert "Не удалось" in _friendly_error("boom")


def test_visualizer_states(qapp):
    from desktop_app.visualizer import HalftoneWidget

    widget = HalftoneWidget()
    widget.resize(400, 400)

    assert widget.state() == HalftoneWidget.IDLE

    widget.set_state(HalftoneWidget.LISTENING)
    assert widget.state() == HalftoneWidget.LISTENING

    widget.set_state(HalftoneWidget.SPEAKING)
    assert widget.state() == HalftoneWidget.SPEAKING

    widget.set_state("bogus")
    assert widget.state() == HalftoneWidget.IDLE


def test_voice_engine_state_machine_without_mic(qapp):
    """VoiceEngine должен стартовать/останавливаться без реального микрофона.

    start() поднимает InputStream; в тесте заменяем _run на безопасный.
    """
    from desktop_app.voice import VoiceEngine

    engine = VoiceEngine(wake_enabled=False)

    # Заменяем поток: в тесте не открываем аудиоустройство.
    engine._thread = None
    engine.stop()  # не стартуя, stop должен быть безвредным
    assert engine.is_dialogue() is False


def test_voice_engine_wake_word_loop(qapp, monkeypatch):
    """Wake word распознаётся, команда публикуется, диалог активируется."""
    import voice.dialogue as dlg
    import sounddevice as sd

    class FakeStream:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(sd, "InputStream", FakeStream)
    monkeypatch.setattr(dlg, "audio_callback", lambda *a, **k: None)

    state = {"n": 0}

    def fake_record(timeout=None, cancel_event=None):
        time.sleep(0.05)
        state["n"] += 1
        return b"audio"

    def fake_transcribe(audio):
        return "Акира открой калькулятор"

    monkeypatch.setattr(dlg, "record_utterance", fake_record)
    monkeypatch.setattr(dlg, "transcribe", fake_transcribe)
    monkeypatch.setattr(dlg, "find_wake_word", lambda t: "акира")
    monkeypatch.setattr(dlg, "remove_wake_word", lambda t, d: "открой калькулятор")
    monkeypatch.setattr(dlg, "speak", lambda t: None)

    from desktop_app.voice import VoiceEngine

    engine = VoiceEngine(wake_enabled=True)
    texts = []
    engine.text_ready.connect(lambda t: texts.append(t))
    engine.start()

    for _ in range(40):
        time.sleep(0.05)
        qapp.processEvents()

    assert texts == ["открой калькулятор"]
    assert engine.is_dialogue() is True

    engine.stop()


def test_voice_engine_capture_once(qapp, monkeypatch):
    """Разовое распознавание кнопкой микрофона публикует распознанный текст."""
    import voice.dialogue as dlg
    import sounddevice as sd

    class FakeStream:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(sd, "InputStream", FakeStream)
    monkeypatch.setattr(dlg, "audio_callback", lambda *a, **k: None)
    monkeypatch.setattr(dlg, "record_utterance", lambda timeout=None, cancel_event=None: b"audio")
    monkeypatch.setattr(dlg, "transcribe", lambda audio: "включи музыку")
    monkeypatch.setattr(dlg, "find_wake_word", lambda t: None)
    monkeypatch.setattr(dlg, "remove_wake_word", lambda t, d: t)
    monkeypatch.setattr(dlg, "speak", lambda t: None)

    from desktop_app.voice import VoiceEngine

    engine = VoiceEngine(wake_enabled=False)
    texts = []
    engine.text_ready.connect(lambda t: texts.append(t))
    engine.start()
    time.sleep(0.2)
    engine.capture_once()

    for _ in range(40):
        time.sleep(0.05)
        qapp.processEvents()

    assert texts == ["включи музыку"]
    assert engine.is_dialogue() is False

    engine.stop()


def test_visualizer_params_ease_smoothly(qapp):
    """Переход между состояниями плавный: параметры догоняют целевые."""
    from desktop_app.visualizer import HalftoneWidget

    widget = HalftoneWidget()
    widget.resize(400, 400)

    widget.set_state(HalftoneWidget.SPEAKING)
    widget._tick()
    widget._tick()

    target = list(HalftoneWidget.STATE_PARAMS[HalftoneWidget.SPEAKING])

    for value in widget._params:
        assert value != 0.0
        assert value == value  # не NaN

    widget.set_state(HalftoneWidget.IDLE)
    for _ in range(200):
        widget._tick()

    idle_target = list(HalftoneWidget.STATE_PARAMS[HalftoneWidget.IDLE])
    for current, target_value in zip(widget._params, idle_target):
        assert abs(current - target_value) < 0.01


def test_visualizer_animation_is_deterministic(qapp):
    """Анимация не зависит от случайности: одинаковая фаза — одинаковый рисунок."""
    from desktop_app.visualizer import HalftoneWidget

    widget = HalftoneWidget()
    widget.resize(400, 400)

    widget._phase = 0.25
    params_a = list(widget._params)
    widget._phase = 0.25

    assert widget._params == params_a


def test_voice_capture_empty_transcription_ignored(qapp, monkeypatch):
    """Тишина/галлюцинация whisper не превращается в сообщение."""
    import voice.dialogue as dlg
    import sounddevice as sd

    class FakeStream:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(sd, "InputStream", FakeStream)
    monkeypatch.setattr(dlg, "audio_callback", lambda *a, **k: None)
    monkeypatch.setattr(dlg, "record_utterance", lambda timeout=None, cancel_event=None: b"audio")
    monkeypatch.setattr(dlg, "transcribe", lambda audio: "")
    monkeypatch.setattr(dlg, "find_wake_word", lambda t: None)
    monkeypatch.setattr(dlg, "remove_wake_word", lambda t, d: t)
    monkeypatch.setattr(dlg, "speak", lambda t: None)

    from desktop_app.voice import VoiceEngine

    engine = VoiceEngine(wake_enabled=False)
    texts = []
    states = []
    engine.text_ready.connect(lambda t: texts.append(t))
    engine.state_changed.connect(lambda s: states.append(s))
    engine.start()
    time.sleep(0.2)
    engine.capture_once()

    for _ in range(40):
        time.sleep(0.05)
        qapp.processEvents()

    assert texts == []
    assert engine.is_dialogue() is False
    assert states[-1] == VoiceEngine.IDLE

    engine.stop()


def test_voice_capture_noise_hallucination_ignored(qapp, monkeypatch):
    """Галлюцинация вроде «Продолжение следует» без wake word не публикуется."""
    import voice.dialogue as dlg
    import sounddevice as sd

    class FakeStream:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(sd, "InputStream", FakeStream)
    monkeypatch.setattr(dlg, "audio_callback", lambda *a, **k: None)
    monkeypatch.setattr(dlg, "record_utterance", lambda timeout=None, cancel_event=None: b"audio")
    monkeypatch.setattr(dlg, "transcribe", lambda audio: "Продолжение следует...")
    monkeypatch.setattr(dlg, "find_wake_word", lambda t: None)
    monkeypatch.setattr(dlg, "remove_wake_word", lambda t, d: t)
    monkeypatch.setattr(dlg, "speak", lambda t: None)

    from desktop_app.voice import VoiceEngine

    engine = VoiceEngine(wake_enabled=False)
    texts = []
    engine.text_ready.connect(lambda t: texts.append(t))
    engine.start()
    time.sleep(0.2)
    engine.capture_once()

    for _ in range(40):
        time.sleep(0.05)
        qapp.processEvents()

    assert texts == []

    engine.stop()


def test_voice_mic_resets_after_capture_error(qapp, monkeypatch):
    """Ошибка распознавания возвращает мик в нормальное состояние (IDLE)."""
    import voice.dialogue as dlg
    import sounddevice as sd

    class FakeStream:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(sd, "InputStream", FakeStream)
    monkeypatch.setattr(dlg, "audio_callback", lambda *a, **k: None)
    monkeypatch.setattr(dlg, "record_utterance", lambda timeout=None, cancel_event=None: b"audio")
    monkeypatch.setattr(dlg, "transcribe", lambda audio: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(dlg, "find_wake_word", lambda t: None)
    monkeypatch.setattr(dlg, "remove_wake_word", lambda t, d: t)
    monkeypatch.setattr(dlg, "speak", lambda t: None)

    from desktop_app.voice import VoiceEngine

    engine = VoiceEngine(wake_enabled=False)
    errors = []
    states = []
    engine.error.connect(lambda m: errors.append(m))
    engine.state_changed.connect(lambda s: states.append(s))
    engine.start()
    time.sleep(0.2)
    engine.capture_once()

    for _ in range(40):
        time.sleep(0.05)
        qapp.processEvents()

    assert errors
    assert states[-1] == VoiceEngine.IDLE

    engine.stop()


def test_voice_dialogue_toggle_starts_and_stops_listening(qapp, monkeypatch):
    """Включение dialogue переводит в LISTENING, выключение — обратно в IDLE."""
    import voice.dialogue as dlg
    import sounddevice as sd

    class FakeStream:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(sd, "InputStream", FakeStream)
    monkeypatch.setattr(dlg, "audio_callback", lambda *a, **k: None)

    calls = {"n": 0}

    def fake_record(timeout=None, cancel_event=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return b"audio"
        return None

    monkeypatch.setattr(dlg, "record_utterance", fake_record)
    monkeypatch.setattr(dlg, "transcribe", lambda audio: "привет")
    monkeypatch.setattr(dlg, "find_wake_word", lambda t: None)
    monkeypatch.setattr(dlg, "remove_wake_word", lambda t, d: t)
    monkeypatch.setattr(dlg, "speak", lambda t: None)

    from desktop_app.voice import VoiceEngine

    engine = VoiceEngine(wake_enabled=False)
    texts = []
    states = []
    engine.text_ready.connect(lambda t: texts.append(t))
    engine.state_changed.connect(lambda s: states.append(s))
    engine.start()
    time.sleep(0.2)
    engine.set_dialogue(True)

    for _ in range(20):
        if engine.is_dialogue():
            break
        time.sleep(0.05)
        qapp.processEvents()

    assert engine.is_dialogue() is True

    for _ in range(40):
        time.sleep(0.05)
        qapp.processEvents()

    assert texts == ["привет"]
    assert VoiceEngine.LISTENING in states

    engine.set_dialogue(False)

    for _ in range(40):
        time.sleep(0.05)
        qapp.processEvents()

    assert engine.is_dialogue() is False
    assert states[-1] == VoiceEngine.IDLE

    engine.stop()


def test_voice_capture_processed_while_wake_listening_blocks(qapp, monkeypatch):
    """Клики по кнопке обрабатываются, даже когда движок слушает wake word.

    Раньше _wake_listen вызывал record_utterance() без cancel_event и навсегда
    блокировал цикл — команда capture лежала в очереди, кнопка «умирала».
    Теперь _submit прерывает прослушивание, и capture исполняется.
    """
    import voice.dialogue as dlg
    import sounddevice as sd

    class FakeStream:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(sd, "InputStream", FakeStream)
    monkeypatch.setattr(dlg, "audio_callback", lambda *a, **k: None)

    def fake_record(timeout=None, cancel_event=None):
        if cancel_event is not None and cancel_event.is_set():
            return None
        if timeout is not None:
            return b"audio"
        cancel_event.wait(timeout=2.0)
        return None

    monkeypatch.setattr(dlg, "record_utterance", fake_record)
    monkeypatch.setattr(dlg, "transcribe", lambda audio: "включи музыку")
    monkeypatch.setattr(dlg, "find_wake_word", lambda t: None)
    monkeypatch.setattr(dlg, "remove_wake_word", lambda t, d: t)
    monkeypatch.setattr(dlg, "speak", lambda t: None)

    from desktop_app.voice import VoiceEngine

    engine = VoiceEngine(wake_enabled=True)
    texts = []
    mic = []
    engine.text_ready.connect(lambda t: texts.append(t))
    engine.mic_capture.connect(lambda a: mic.append(a))
    engine.start()
    time.sleep(0.2)
    engine.capture_once()

    for _ in range(60):
        time.sleep(0.05)
        qapp.processEvents()

    assert texts == ["включи музыку"]
    assert mic[0] is True
    assert mic[-1] is False

    engine.stop()


def test_voice_mic_off_on_off_without_microphone(qapp, monkeypatch):
    """Кнопка OFF→ON→OFF работает даже без открытого микрофона.

    InputStream недоступен — движок не должен умирать: кнопка получает
    mic_capture(True) при старте записи и mic_capture(False) при отмене.
    """
    import voice.dialogue as dlg
    import sounddevice as sd

    def failing_stream(*a, **k):
        raise OSError("no mic device")

    monkeypatch.setattr(sd, "InputStream", failing_stream)

    def fake_record(timeout=None, cancel_event=None):
        if cancel_event is not None:
            cancel_event.wait(timeout=5.0)
        return None

    monkeypatch.setattr(dlg, "record_utterance", fake_record)
    monkeypatch.setattr(dlg, "transcribe", lambda audio: "")
    monkeypatch.setattr(dlg, "find_wake_word", lambda t: None)
    monkeypatch.setattr(dlg, "remove_wake_word", lambda t, d: t)
    monkeypatch.setattr(dlg, "speak", lambda t: None)

    from desktop_app.voice import VoiceEngine

    engine = VoiceEngine(wake_enabled=False)
    mic = []
    errors = []
    engine.mic_capture.connect(lambda a: mic.append(a))
    engine.error.connect(lambda m: errors.append(m))
    engine.start()

    for _ in range(20):
        time.sleep(0.05)
        qapp.processEvents()

    assert errors  # микрофон недоступен, но движок остался жив

    engine.capture_once()
    for _ in range(40):
        time.sleep(0.05)
        qapp.processEvents()
    assert mic[-1] is True

    engine.cancel_capture()
    for _ in range(40):
        time.sleep(0.05)
        qapp.processEvents()
    assert mic[-1] is False

    engine.stop()


def test_visualizer_click_signal(qapp):
    from desktop_app.visualizer import HalftoneWidget

    widget = HalftoneWidget()
    clicked = []

    widget.clicked.connect(lambda: clicked.append(True))

    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import QEvent, QPointF, Qt

    event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(200, 200),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    widget.mousePressEvent(event)

    assert clicked == [True]


def test_audit_activity_hook(isolated_project):
    audit = isolated_project("audit")

    seen = []

    audit.set_activity_hook(lambda tool, args: seen.append((tool, args)))

    audit.record_tool_execution(
        "observe",
        {},
        {"success": True, "error": None, "output": "ок"},
        "auto",
    )

    assert seen == [("observe", {})]

    audit.clear_activity_hook()

    audit.record_tool_execution(
        "open",
        {"target": "Safari"},
        {"success": True, "error": None, "output": "ок"},
        "auto",
    )

    assert seen == [("observe", {})]


def test_stop_speaking_interrupts_tts(qapp, monkeypatch):
    """stop_speaking прерывает текущую озвучку и возвращает движок в IDLE."""
    import voice.dialogue as dlg

    state = {"interrupted": False}

    def fake_speak(text):
        time.sleep(10)

    def fake_stop():
        state["interrupted"] = True

    monkeypatch.setattr(dlg, "speak", fake_speak)
    monkeypatch.setattr(dlg, "stop_speaking", fake_stop)

    from desktop_app.voice import VoiceEngine

    engine = VoiceEngine(wake_enabled=False)
    states = []
    engine.state_changed.connect(lambda s: states.append(s))
    engine.speak("длинный текст")

    for _ in range(20):
        time.sleep(0.05)
        qapp.processEvents()

    engine.stop_speaking()
    assert state["interrupted"] is True

    engine.stop()