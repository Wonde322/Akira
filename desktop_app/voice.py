"""Always-armed voice input for desktop Akira."""
from __future__ import annotations

import queue
import threading
import time

import voice.dialogue as dlg
from voice.dialogue import VoiceConfigurationError, _is_hallucination
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
        self._commands = queue.Queue()
        self._stop_event = threading.Event()
        self._interrupt = threading.Event()
        self._cancel_event = threading.Event()
        self._thread = None
        self._audio_ok = False
        self._listening = True
        self._stop = False

    def start(self):
        if self._thread and self._thread.is_alive(): return
        self._stop = False; self._listening = True
        self._stop_event.clear(); self._interrupt.clear(); self._cancel_event.clear()
        self._commands = queue.Queue(); dlg.clear_audio_queue()
        self._thread = threading.Thread(target=self._run, name="akira-voice", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop = True; self._stop_event.set(); self._interrupt.set(); self._set_dialogue(False)
        self._commands.put(("stop", None))
        thread = self._thread
        if thread and thread is not threading.current_thread(): thread.join(timeout=3)
        if thread is None or not thread.is_alive(): self._thread = None
        dlg.clear_audio_queue(); self._audio_ok = False; self._listening = False

    def _put(self, kind, payload=None):
        self._interrupt.set(); self._commands.put((kind, payload))
    def capture_once(self): self._put("capture")
    def cancel_capture(self): self._cancel_event.set(); self._put("cancel")
    def set_dialogue(self, enabled): self._put("dialogue", bool(enabled))
    def set_wake_enabled(self, enabled): self._put("wake", bool(enabled))
    def speak(self, text): self._put("speak", str(text))
    def stop_speaking(self): dlg.stop_speaking()
    def pause(self): self._listening = False; self._interrupt.set()
    def resume(self): self._listening = True; self._interrupt.set()
    def is_dialogue(self): return self._dialogue
    def end_turn(self): self._put("end_turn")

    def _set_dialogue(self, value):
        value = bool(value)
        if value != self._dialogue:
            self._dialogue = value; self.dialogue_changed.emit(value)

    def _emit_state(self, state): self.state_changed.emit(state)

    def _safe_transcribe(self, dialogue, audio):
        try: text = dialogue.transcribe(audio)
        except Exception as exc:
            self.error.emit(str(exc) or "Не удалось распознать речь."); return ""
        if not text or _is_hallucination(text): return ""
        return str(text).strip()

    def _speak(self, dialogue, text):
        self._listening = False; self._emit_state(self.SPEAKING)
        try: dialogue.speak(text)
        finally: self._listening = True; self._emit_state(self.IDLE)

    def _capture(self, dialogue=None):
        dialogue = dialogue or dlg; self._cancel_event.clear()
        try: dialogue.clear_audio_queue()
        except AttributeError: pass
        self._listening = False; self.mic_capture.emit(True); self._emit_state(self.LISTENING)
        try: audio = dialogue.record_utterance(timeout=dialogue.DIALOGUE_TIMEOUT, cancel_event=self._cancel_event)
        except Exception as exc:
            self.error.emit(str(exc) or "Не удалось записать речь."); audio = None
        finally: self.mic_capture.emit(False)
        if audio is None:
            self._emit_state(self.IDLE); self._listening = True; return
        text = self._safe_transcribe(dialogue, audio)
        if text:
            self._emit_state(self.THINKING); self.text_ready.emit(text); return
        self._listening = True; self._emit_state(self.IDLE)

    def _wake_listen(self, dialogue=None):
        dialogue = dialogue or dlg
        if not self._audio_ok: return
        self._listening = True; self._emit_state(self.LISTENING)
        try:
            audio = dialogue.record_utterance(timeout=getattr(dialogue, "WAKE_TIMEOUT", None), end_silence_ms=getattr(dialogue, "WAKE_END_SILENCE_MS", None), cancel_event=self._interrupt)
        except TypeError:
            try: audio = dialogue.record_utterance(cancel_event=self._interrupt)
            except Exception: return
        except Exception: return
        if not audio: return
        text = self._safe_transcribe(dialogue, audio)
        if not text: return
        detected = dialogue.find_wake_word(text)
        if detected is None: return
        self._set_dialogue(True)
        command = dialogue.remove_wake_word(text, detected)
        if not command:
            self._speak(dialogue, "Да?"); return
        self._listening = False; self._emit_state(self.THINKING); self.text_ready.emit(command)

    def _dialogue_listen(self, dialogue=None):
        dialogue = dialogue or dlg
        if not self._audio_ok: return
        self._listening = True; self._emit_state(self.LISTENING)
        try: audio = dialogue.record_utterance(timeout=dialogue.DIALOGUE_TIMEOUT, cancel_event=self._interrupt)
        except TypeError:
            try: audio = dialogue.record_utterance(cancel_event=self._interrupt)
            except Exception: audio = None
        except Exception: audio = None
        if not audio:
            self._set_dialogue(False); self._listening = True; self._emit_state(self.IDLE); return
        text = self._safe_transcribe(dialogue, audio)
        if not text:
            self._set_dialogue(False); self._listening = True; self._emit_state(self.IDLE); return
        self._listening = False; self._emit_state(self.THINKING); self.text_ready.emit(text)

    def _run(self):
        import sounddevice as sd
        stream = None
        try:
            stream = sd.InputStream(samplerate=dlg.SAMPLE_RATE, channels=1, dtype="float32", blocksize=dlg.FRAME_SAMPLES, callback=dlg.audio_callback)
            stream.__enter__(); self._audio_ok = True
        except Exception:
            self.error.emit("Не удалось открыть микрофон. Проверь разрешение macOS для приложения Akira.")
        try:
            while not self._stop_event.is_set():
                try: kind, payload = self._commands.get_nowait()
                except queue.Empty: kind = payload = None
                if kind:
                    self._interrupt.clear()
                    if kind == "stop": break
                    if kind == "wake": self._wake_enabled = bool(payload); self._listening = True; continue
                    if kind == "dialogue": self._set_dialogue(payload); self._listening = bool(payload); continue
                    if kind == "end_turn": self._set_dialogue(False); self._listening = True; continue
                    if kind == "cancel": self.mic_capture.emit(False); self._listening = True; continue
                    if kind == "capture": self._capture(); continue
                    if kind == "speak": self._speak(dlg, payload); continue
                if not self._audio_ok or not self._listening:
                    time.sleep(0.02); continue
                if self._dialogue: self._dialogue_listen()
                elif self._wake_enabled: self._wake_listen()
                else: time.sleep(0.02)
        finally:
            self._audio_ok = False; self._listening = False
            if stream:
                try: stream.__exit__(None, None, None)
                except Exception: pass
            self._thread = None
