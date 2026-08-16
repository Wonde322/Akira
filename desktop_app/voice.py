"""Голосовой движок desktop-приложения.

Владеет собственным потоком и состоянием:
- разовое распознавание кнопкой микрофона (capture_once);
- dialogue mode по клику на сферу (set_dialogue);
- фоновый wake-word listener (set_wake_enabled).

Правила надёжности:
- тишина/пустая транскрипция никогда не превращается в сообщение;
- после любого завершения (success/error/cancel/timeout) движок возвращается
  в корректное состояние, никаких stuck states;
- audio/TTS работают только в потоке движка, GUI не блокируется.
"""

import queue
import threading
import time

import voice.dialogue as dlg
from voice.dialogue import _is_hallucination

from PySide6.QtCore import QObject, Signal


class VoiceEngine(QObject):
    """Поток с InputStream; публикует распознанный текст и состояние."""

    text_ready = Signal(str)
    state_changed = Signal(str)
    error = Signal(str)
    mic_capture = Signal(bool)
    dialogue_changed = Signal(bool)

    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"

    def __init__(self, wake_enabled=True, parent=None):
        super().__init__(parent)
        self._wake_enabled = wake_enabled
        self._dialogue = False
        self._listening = True
        self._capture_requested = False
        self._commands = queue.Queue()
        self._stop_event = threading.Event()
        self._cancel_event = threading.Event()
        self._interrupt = threading.Event()
        self._audio_ok = False
        self._thread = None

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(
                target=self._run,
                daemon=True,
                name="voice-engine",
            )
            self._thread.start()

    def stop(self):
        self._stop_event.set()
        self._interrupt.set()
        self._commands.put(("stop", None))

        if self._thread is not None:
            self._thread.join(timeout=3)

    def _submit(self, kind, payload=None):
        """Ставит команду и прерывает текущее прослушивание.

        Внутренний цикл движка может быть заблокирован в record_utterance
        (прослушивание wake word / диалога). Без прерывания команда лежала бы
        в очереди, пока слушающий цикл не вернётся сам — клики по кнопке и
        сфере выглядели бы мёртвыми. interrupt заставляет record_utterance
        вернуться немедленно, после чего цикл читает команду из очереди.
        """
        self._interrupt.set()
        self._commands.put((kind, payload))

    # ------------------------------------------------------------------ API
    def capture_once(self):
        """Разовое распознавание (кнопка микрофона)."""
        self._submit("capture")

    def cancel_capture(self):
        """Прерывает текущую запись разового распознавания."""
        self._cancel_event.set()
        self._submit("cancel")

    def set_dialogue(self, enabled):
        self._submit("dialogue", enabled)

    def set_wake_enabled(self, enabled):
        self._submit("wake", enabled)

    def speak(self, text):
        self._submit("speak", text)

    def stop_speaking(self):
        """Прерывает текущую озвучку TTS."""
        dlg.stop_speaking()

    def pause(self):
        """Говорит движку перестать слушать (ждём ответа)."""
        self._submit("pause")

    def resume(self):
        """Возобновляет прослушивание после ответа."""
        self._submit("resume")

    def is_dialogue(self):
        return self._dialogue

    # ------------------------------------------------------------- internals
    def _emit_state(self, state):
        self.state_changed.emit(state)

    def _run(self):
        import sounddevice as sd

        self._emit_state(self.IDLE)

        stream = None
        try:
            stream = sd.InputStream(
                samplerate=dlg.SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=dlg.FRAME_SAMPLES,
                callback=dlg.audio_callback,
            )
            stream.__enter__()
            self._audio_ok = True
        except Exception as error:
            stream = None
            self._audio_ok = False
            print("Микрофон недоступен:", error)
            if not self._stop_event.is_set():
                self.error.emit(
                    "Не удалось открыть микрофон. Проверь доступ в Настройках."
                )

        try:
            self._loop(dlg)
        finally:
            if stream is not None:
                stream.__exit__(None, None, None)

    def _loop(self, dlg):
        while not self._stop_event.is_set():
            cmd = None

            try:
                cmd = self._commands.get(timeout=0.05)
            except queue.Empty:
                pass

            if cmd is not None:
                # Команда получена: прерывание больше не нужно, следующее
                # прослушивание стартует с чистого состояния.
                self._interrupt.clear()
                kind, payload = cmd

                if kind == "stop":
                    break
                if kind == "speak":
                    self._speak(dlg, payload)
                    continue
                if kind == "capture":
                    self._capture(dlg)
                    continue
                if kind == "cancel":
                    self._cancel_event.set()
                    self.mic_capture.emit(False)
                    self._emit_state(self.IDLE)
                    continue
                if kind == "dialogue":
                    self._dialogue = bool(payload)
                    self.dialogue_changed.emit(self._dialogue)
                    if not self._dialogue:
                        self._emit_state(self.IDLE)
                    continue
                if kind == "wake":
                    self._wake_enabled = bool(payload)
                    continue
                if kind == "pause":
                    self._listening = False
                    continue
                if kind == "resume":
                    self._listening = True
                    continue

            if not self._listening:
                time.sleep(0.05)
                continue

            if self._dialogue:
                self._dialogue_listen(dlg)
            elif self._wake_enabled:
                self._wake_listen(dlg)
            else:
                time.sleep(0.1)

    def _speak(self, dlg, text):
        self._emit_state(self.SPEAKING)
        try:
            dlg.speak(text)
        finally:
            # После речи возвращаем прослушивание и состояние.
            self._listening = True
            self._emit_state(self.IDLE)

    def _capture(self, dlg):
        self._cancel_event.clear()
        self._emit_state(self.LISTENING)
        self.mic_capture.emit(True)
        try:
            # Без открытого потока record_utterance просто дождётся таймаута
            # или отмены (повторный клик) — кнопка остаётся ON, пока не
            # вернёмся. Это позволяет проверить OFF→ON→OFF без разрешения.
            audio = dlg.record_utterance(
                timeout=dlg.DIALOGUE_TIMEOUT,
                cancel_event=self._cancel_event,
            )
        except Exception as error:
            print("Capture error:", error)
            audio = None
        finally:
            # Кнопка обязана вернуться в OFF при любом завершении записи.
            self.mic_capture.emit(False)

        if audio is None:
            self._emit_state(self.IDLE)
            return

        text = self._safe_transcribe(dlg, audio)

        if not text:
            self._emit_state(self.IDLE)
            return

        self._listening = False
        self._emit_state(self.THINKING)
        self.text_ready.emit(text)

    def _dialogue_listen(self, dlg):
        self._emit_state(self.LISTENING)
        if not self._audio_ok:
            time.sleep(0.2)
            return
        audio = dlg.record_utterance(
            timeout=dlg.DIALOGUE_TIMEOUT,
            cancel_event=self._interrupt,
        )

        if audio is None:
            # Тишина в диалоге — остаёмся слушать, пока dialogue включён.
            self._emit_state(self.LISTENING)
            return

        text = self._safe_transcribe(dlg, audio)

        if not text:
            self._emit_state(self.LISTENING)
            return

        self._listening = False
        self._emit_state(self.THINKING)
        self.text_ready.emit(text)

    def _wake_listen(self, dlg):
        if not self._audio_ok:
            time.sleep(0.2)
            return
        audio = dlg.record_utterance(cancel_event=self._interrupt)

        if audio is None:
            return

        text = self._safe_transcribe(dlg, audio)

        if not text:
            return

        detected = dlg.find_wake_word(text)

        if detected is None:
            return

        self._dialogue = True
        self.dialogue_changed.emit(True)
        command = dlg.remove_wake_word(text, detected)

        if command:
            self._listening = False
            self._emit_state(self.THINKING)
            self.text_ready.emit(command)
        else:
            self._speak(dlg, "Да?")

    def _safe_transcribe(self, dlg, audio):
        try:
            text = dlg.transcribe(audio)
        except Exception as error:
            self.error.emit("Не удалось распознать речь.")
            print("Whisper error:", error)
            return ""

        if _is_hallucination(text):
            return ""

        return text