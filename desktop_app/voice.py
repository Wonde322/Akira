"""Always-armed voice input for desktop Akira."""
import queue, threading, time
import voice.dialogue as dlg
from voice.dialogue import VoiceConfigurationError, _is_hallucination
from PySide6.QtCore import QObject, Signal

class VoiceEngine(QObject):
    text_ready=Signal(str); state_changed=Signal(str); error=Signal(str); mic_capture=Signal(bool); dialogue_changed=Signal(bool)
    IDLE="idle"; LISTENING="listening"; THINKING="thinking"; SPEAKING="speaking"
    def __init__(self,wake_enabled=True,parent=None):
        super().__init__(parent); self._wake_enabled=wake_enabled; self._dialogue=False; self._commands=queue.Queue(); self._stop=threading.Event(); self._interrupt=threading.Event(); self._cancel=threading.Event(); self._thread=None; self._audio_ok=False
    def start(self):
        if self._thread and self._thread.is_alive():return
        self._stop.clear(); self._interrupt.clear(); self._cancel.clear(); self._commands=queue.Queue(); dlg.clear_audio_queue(); self._thread=threading.Thread(target=self._run,name="akira-voice",daemon=True); self._thread.start()
    def stop(self):
        self._stop.set(); self._interrupt.set(); self._commands.put(("stop",None));
        if self._thread and self._thread is not threading.current_thread():self._thread.join(timeout=3)
        dlg.clear_audio_queue(); self._audio_ok=False
    def _put(self,kind,payload=None): self._interrupt.set(); self._commands.put((kind,payload))
    def capture_once(self): self._put("capture")
    def cancel_capture(self): self._cancel.set(); self._put("cancel")
    def set_dialogue(self,enabled): self._put("dialogue",bool(enabled))
    def set_wake_enabled(self,enabled): self._put("wake",bool(enabled))
    def speak(self,text): self._put("speak",str(text))
    def stop_speaking(self): dlg.stop_speaking()
    def pause(self): pass
    def resume(self): self._interrupt.set()  # wake a blocked listen; input is never disabled
    def is_dialogue(self): return self._dialogue
    def end_turn(self): self._put("end_turn")
    def _set_dialogue(self,value):
        value=bool(value)
        if value!=self._dialogue:self._dialogue=value; self.dialogue_changed.emit(value)
    def _run(self):
        import sounddevice as sd
        stream=None
        try:
            stream=sd.InputStream(samplerate=dlg.SAMPLE_RATE,channels=1,dtype="float32",blocksize=dlg.FRAME_SAMPLES,callback=dlg.audio_callback); stream.__enter__(); self._audio_ok=True
        except Exception:
            self.error.emit("Не удалось открыть микрофон. Проверь разрешение macOS для приложения Akira.")
        try:
            while not self._stop.is_set():
                try:kind,payload=self._commands.get_nowait()
                except queue.Empty:kind=payload=None
                if kind:
                    self._interrupt.clear()
                    if kind=="stop":break
                    if kind=="wake":self._wake_enabled=bool(payload); continue
                    if kind=="dialogue":self._set_dialogue(payload); continue
                    if kind=="end_turn":self._set_dialogue(False); continue
                    if kind=="cancel":self.mic_capture.emit(False); continue
                    if kind=="capture":self._capture(); continue
                    if kind=="speak":self.state_changed.emit(self.SPEAKING); dlg.speak(payload); self.state_changed.emit(self.IDLE); continue
                if not self._audio_ok: time.sleep(.2); continue
                self._listen()
        finally:
            self._audio_ok=False
            if stream:
                try:stream.__exit__(None,None,None)
                except Exception:pass
    def _capture(self):
        self._cancel.clear(); dlg.clear_audio_queue(); self.mic_capture.emit(True); self.state_changed.emit(self.LISTENING)
        try: audio=dlg.record_utterance(timeout=dlg.DIALOGUE_TIMEOUT,cancel_event=self._cancel)
        except Exception: audio=None
        finally:self.mic_capture.emit(False)
        self._emit(audio,require_wake=False)
    def _listen(self):
        self.state_changed.emit(self.LISTENING)
        try: audio=dlg.record_utterance(timeout=dlg.DIALOGUE_TIMEOUT if self._dialogue else None,cancel_event=self._interrupt)
        except TypeError: audio=dlg.record_utterance(cancel_event=self._interrupt)
        except Exception:return
        if audio is None:
            if self._dialogue:self._set_dialogue(False)
            return
        self._emit(audio,require_wake=not self._dialogue)
    def _emit(self,audio,require_wake):
        try:text=dlg.transcribe(audio)
        except VoiceConfigurationError as e:self.error.emit(str(e)); return
        except Exception:self.error.emit("Не удалось распознать речь."); return
        if not text or _is_hallucination(text):return
        if require_wake:
            detected=dlg.find_wake_word(text)
            if detected is None:return
            self._set_dialogue(True); text=dlg.remove_wake_word(text,detected)
            if not text: dlg.speak("Да?"); return
        self.state_changed.emit(self.THINKING); self.text_ready.emit(text)
