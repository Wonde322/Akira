"""Voice engine for the desktop application."""

import queue
import threading
import time

import voice.dialogue as dlg
from voice.dialogue import _is_hallucination
from PySide6.QtCore import QObject, Signal


class VoiceEngine(QObject):
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
        self._commands = queue.Queue()
        self._stop_event = threading.Event()
        self._cancel_event = threading.Event()
        self._interrupt = threading.Event()
        self._audio_ok = False
        self._thread = None

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, daemon=True, name="voice-engine")
            self._thread.start()

    def stop(self):
        self._stop_event.set()
        self._interrupt.set()
        self._commands.put(("stop", None))
        if self._thread is not None:
            self._thread.join(timeout=3)

    def _submit(self, kind, payload=None):
        self._interrupt.set()
        self._commands.put((kind, payload))

    def capture_once(self): self._submit("capture")
    def cancel_capture(self): self._cancel_event.set(); self._submit("cancel")
    def set_dialogue(self, enabled): self._submit("dialogue", enabled)
    def set_wake_enabled(self, enabled): self._submit("wake", enabled)
    def speak(self, text): self._submit("speak", text)
    def stop_speaking(self): dlg.stop_speaking()
    def pause(self): self._submit("pause")
    def resume(self): self._submit("resume")
    def is_dialogue(self): return self._dialogue

    def end_turn(self):
        """Finish the current voice turn and return to background wake listening."""
        self._submit("end_turn")

    def _emit_state(self, state): self.state_changed.emit(state)

    def _run(self):
        import sounddevice as sd
        self._emit_state(self.IDLE)
        stream = None
        try:
            stream = sd.InputStream(samplerate=dlg.SAMPLE_RATE, channels=1, dtype="float32", blocksize=dlg.FRAME_SAMPLES, callback=dlg.audio_callback)
            stream.__enter__()
            self._audio_ok = True
        except Exception as error:
            self._audio_ok = False
            print("Микрофон недоступен:", error)
            if not self._stop_event.is_set():
                self.error.emit("Не удалось открыть микрофон. Проверь доступ в Настройках.")
        try:
            self._loop(dlg)
        finally:
            if stream is not None:
                stream.__exit__(None, None, None)

    def _loop(self, dlg):
        while not self._stop_event.is_set():
            try:
                kind, payload = self._commands.get(timeout=0.05)
            except queue.Empty:
                kind = payload = None
            if kind is not None:
                self._interrupt.clear()
                if kind == "stop": break
                if kind == "speak": self._speak(dlg, payload); continue
                if kind == "capture": self._capture(dlg); continue
                if kind == "cancel":
                    self._cancel_event.set(); self.mic_capture.emit(False); self._emit_state(self.IDLE); continue
                if kind == "dialogue":
                    self._set_dialogue(bool(payload))
                    if not self._dialogue: self._emit_state(self.IDLE)
                    continue
                if kind == "end_turn":
                    self._set_dialogue(False); self._listening = True; self._emit_state(self.IDLE); continue
                if kind == "wake": self._wake_enabled = bool(payload); continue
                if kind == "pause": self._listening = False; continue
                if kind == "resume": self._listening = True; continue
            if not self._listening:
                time.sleep(0.05); continue
            if self._dialogue: self._dialogue_listen(dlg)
            elif self._wake_enabled: self._wake_listen(dlg)
            else: time.sleep(0.1)

    def _set_dialogue(self, enabled):
        enabled = bool(enabled)
        if enabled != self._dialogue:
            self._dialogue = enabled
            self.dialogue_changed.emit(enabled)

    def _speak(self, dlg, text):
        self._emit_state(self.SPEAKING)
        try: dlg.speak(text)
        finally:
            self._listening = True
            self._emit_state(self.IDLE)

    def _capture(self, dlg):
        self._cancel_event.clear(); self._emit_state(self.LISTENING); self.mic_capture.emit(True)
        try: audio = dlg.record_utterance(timeout=dlg.DIALOGUE_TIMEOUT, cancel_event=self._cancel_event)
        except Exception as error:
            print("Capture error:", error); audio = None
        finally: self.mic_capture.emit(False)
        if audio is None:
            self._emit_state(self.IDLE); return
        text = self._safe_transcribe(dlg, audio)
        if not text:
            self._emit_state(self.IDLE); return
        self._listening = False; self._emit_state(self.THINKING); self.text_ready.emit(text)

    def _dialogue_listen(self, dlg):
        self._emit_state(self.LISTENING)
        if not self._audio_ok: time.sleep(0.2); return
        audio = dlg.record_utterance(timeout=dlg.DIALOGUE_TIMEOUT, cancel_event=self._interrupt)
        if audio is None:
            self._set_dialogue(False); self._emit_state(self.IDLE); return
        text = self._safe_transcribe(dlg, audio)
        if not text:
            self._set_dialogue(False); self._emit_state(self.IDLE); return
        self._listening = False; self._emit_state(self.THINKING); self.text_ready.emit(text)

    def _wake_listen(self, dlg):
        if not self._audio_ok: time.sleep(0.2); return
        try:
            audio = dlg.record_utterance(
                cancel_event=self._interrupt,
                end_silence_ms=getattr(dlg, "WAKE_END_SILENCE_MS", 450),
            )
        except TypeError:
            # Keep compatibility with older implementations and lightweight test fakes.
            audio = dlg.record_utterance(cancel_event=self._interrupt)
        if audio is None: return
        text = self._safe_transcribe(dlg, audio)
        if not text: return
        detected = dlg.find_wake_word(text)
        if detected is None: return
        self._set_dialogue(True)
        command = dlg.remove_wake_word(text, detected)
        if command:
            self._listening = False; self._emit_state(self.THINKING); self.text_ready.emit(command)
        else:
            self._speak(dlg, "Да?")

    def _safe_transcribe(self, dlg, audio):
        try: text = dlg.transcribe(audio)
        except Exception as error:
            self.error.emit("Не удалось распознать речь."); print("Whisper error:", error); return ""
        if _is_hallucination(text): return ""
        return text
