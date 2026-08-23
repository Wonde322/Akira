"""Desktop command surface with interruptible input and clean user output."""
from __future__ import annotations
import json,re
from .proactive_surface import ProactiveDesktopBridge
from .window import MainWindow

class ProactiveMainWindow(MainWindow):
    _WAKE={"акира","akira"}
    _INTERNAL=("проверка контекста","проверяю контекст","checking context","checking current context","verification","evidence")
    def __init__(self,parent=None):
        super().__init__(parent); self.worker.acknowledged.connect(self._ack)
        self.proactive_surface=ProactiveDesktopBridge(parent=self); self.proactive_surface.notification.connect(self._notification); self.proactive_surface.question.connect(self._question); self.proactive_surface.start()
    @classmethod
    def _wake_only(cls,text):
        return str(text).strip(" .,!?;:").casefold() in cls._WAKE
    @classmethod
    def _clean(cls,value):
        text=str(value or "").strip()
        if not text:return ""
        low=text.casefold()
        if any(token in low for token in cls._INTERNAL): return ""
        try:
            decoded=json.loads(text)
            if isinstance(decoded,(dict,list)): return ""
        except Exception:pass
        return text
    def _set_state(self,state):
        super()._set_state(state)
        if state!=self.DISABLED:self.input.setEnabled(True)
    def _ack(self,message):
        self._append_message("Делаю.","akira"); self.status.setText("Выполняю.")
    def _submit_to_worker(self,message,voice=False):
        message=str(message).strip()
        if not message:return
        self._append_message(message,"user"); self._last_voice=bool(voice); self.worker.submit(message); self.voice.resume(); self._set_state(self.THINKING)
    def _on_submit(self,message):
        if self._wake_only(message): self.voice.set_dialogue(True); self.status.setText("Слушаю."); return
        if self._state==self.SPEAKING:self.voice.stop_speaking()
        if self.proactive_surface.active_question_id is not None:
            result=self.proactive_surface.answer(message)
            if result.get("success"):return
        self._submit_to_worker(message)
    def _on_voice_text(self,text):
        if self._wake_only(text): self.voice.set_dialogue(True); return
        self._submit_to_worker(text,voice=True)
    def _on_answer(self,answer):
        answer=self._clean(answer)
        if not answer: answer="Готово."
        super()._on_answer(answer)
        self.voice.resume()
    def _on_error(self,message):
        super()._on_error(message); self.voice.resume()
    def _on_activity(self,label):
        text=self._clean(label)
        if text: super()._on_activity(text)
    def _notification(self,item):
        text=self._clean(item.get("message") or item.get("text") or item.get("title"))
        if text:self._append_message(text,"akira")
    def _question(self,item):
        text=self._clean(item.get("message") or item.get("text") or item.get("title"))
        if text:self._append_message(text,"akira")
    def _on_mic_clicked(self):
        if self._state==self.DISABLED:return
        if self._state==self.SPEAKING:self.voice.stop_speaking()
        if self._mic_active:self.voice.cancel_capture(); return
        self.voice.capture_once()
    def closeEvent(self,event):
        self.proactive_surface.stop(); super().closeEvent(event)
