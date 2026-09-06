import collections
import os
import queue
import re
import tempfile
import threading
import time

import numpy as np
import sounddevice as sd
import soundfile as sf
import webrtcvad

from akira_gateway import create_gateway
from config import create_groq_client
from permissions import deny_all, set_confirmation_provider

set_confirmation_provider(deny_all)

SAMPLE_RATE = 16000
FRAME_MS = 30
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000
VAD_MODE = 1
END_SILENCE_MS = 1200
WAKE_END_SILENCE_MS = 450
PRE_ROLL_MS = 450
MAX_UTTERANCE_MS = 15000
DIALOGUE_TIMEOUT = 8

vad = webrtcvad.Vad(VAD_MODE)
client = None
gateway = None
audio_queue = queue.Queue(maxsize=200)
speaking = False
speak_proc = None
_speak_lock = threading.Lock()

WAKE_VARIANTS = {"акира", "кира", "акера", "акиро", "акыра", "акираа", "акирах", "акйра", "акирая"}

_HALLUCINATIONS = (
    "продолжение следует", "если понадобится продолжить или есть вопросы",
    "дай знать если понадобится продолжить", "большое спасибо за просмотр",
    "спасибо за просмотр", "подпишись на канал", "нажми подписаться",
    "не забывайте подписываться", "возможные варианты имени",
    "не придумывай текст если речи нет", "имя голосового ассистента",
)


class VoiceConfigurationError(RuntimeError):
    pass


def _ensure_client():
    global client
    if client is None:
        try:
            client = create_groq_client()
        except KeyError as error:
            raise VoiceConfigurationError(
                "Не задан GROQ_API_KEY: распознавание речи не может подключиться к Groq."
            ) from error
    return client


def _get_gateway():
    global gateway
    if gateway is None:
        gateway = create_gateway()
    return gateway


def _is_hallucination(text):
    if not text:
        return False
    normalized = text.lower().replace("ё", "е")
    return any(phrase in normalized for phrase in _HALLUCINATIONS)


def speak(text):
    global speaking, speak_proc
    if not text:
        return
    speaking = True
    clear_audio_queue()
    print("АКИРА:", text)
    try:
        import subprocess
        from config import TTS_VOICE
        proc = subprocess.Popen(["say", "-v", TTS_VOICE, text])
        with _speak_lock:
            speak_proc = proc
        proc.wait()
    finally:
        with _speak_lock:
            speak_proc = None
        clear_audio_queue()
        speaking = False


def stop_speaking():
    with _speak_lock:
        proc = speak_proc
    if proc is not None:
        proc.terminate()


def audio_callback(indata, frames, time_info, status):
    if status:
        print("Audio:", status)
    if speaking or indata is None:
        return
    try:
        frame = np.asarray(indata[:, 0], dtype=np.float32).copy()
        if frame.size != FRAME_SAMPLES:
            return
        try:
            audio_queue.put_nowait(frame)
        except queue.Full:
            try:
                audio_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                audio_queue.put_nowait(frame)
            except queue.Full:
                pass
    except Exception as error:
        print("Audio callback error:", error)


def is_speech(frame):
    array = np.asarray(frame, dtype=np.float32)
    if array.size != FRAME_SAMPLES:
        return False
    pcm = np.clip(array, -1.0, 1.0)
    pcm = np.asarray(pcm * 32767, dtype=np.int16)
    try:
        return vad.is_speech(pcm.tobytes(), SAMPLE_RATE)
    except Exception:
        return False


def clear_audio_queue():
    while True:
        try:
            audio_queue.get_nowait()
        except queue.Empty:
            return


def record_utterance(timeout=None, cancel_event=None, end_silence_ms=None):
    pre_roll = collections.deque(maxlen=max(1, PRE_ROLL_MS // FRAME_MS))
    silence_ms = END_SILENCE_MS if end_silence_ms is None else end_silence_ms
    silence_limit = max(1, int(silence_ms) // FRAME_MS)
    max_frames = MAX_UTTERANCE_MS // FRAME_MS
    recording = False
    frames = []
    silence_count = 0
    started_at = time.monotonic()
    while True:
        if cancel_event is not None and cancel_event.is_set():
            return None
        if timeout is not None and time.monotonic() - started_at > timeout:
            return None
        try:
            frame = audio_queue.get(timeout=0.2)
        except queue.Empty:
            continue
        speech = is_speech(frame)
        if not recording:
            pre_roll.append(frame)
            if speech:
                recording = True
                frames.extend(pre_roll)
                silence_count = 0
        else:
            frames.append(frame)
            silence_count = 0 if speech else silence_count + 1
            if silence_count >= silence_limit or len(frames) >= max_frames:
                break
    return np.concatenate(frames) if frames else None


def transcribe(audio):
    if audio is None or not len(audio):
        return ""
    filename = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            filename = handle.name
        sf.write(filename, audio, SAMPLE_RATE)
        with open(filename, "rb") as audio_file:
            result = _ensure_client().audio.transcriptions.create(
                file=(os.path.basename(filename), audio_file.read()),
                model="whisper-large-v3",
                language="ru",
                temperature=0,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
                prompt="Русская речь пользователя. Не придумывай текст, если речи нет.",
            )
        text = (result.text or "").strip()
        if _is_hallucination(text):
            return ""
        segments = getattr(result, "segments", None) or []
        if segments:
            no_speech = max(float(getattr(s, "no_speech_prob", 0)) for s in segments)
            avg_logprob = min(float(getattr(s, "avg_logprob", 0)) for s in segments)
            if no_speech > 0.70 or avg_logprob < -1.2:
                return ""
        return text
    finally:
        if filename and os.path.exists(filename):
            os.unlink(filename)


def find_wake_word(text):
    if not isinstance(text, str):
        return None
    normalized = text.lower().replace("ё", "е")
    for word in re.findall(r"[а-яa-z0-9_]+", normalized):
        if word in WAKE_VARIANTS:
            return word
        if len(word) >= 4:
            for variant in WAKE_VARIANTS:
                if abs(len(word) - len(variant)) > 1:
                    continue
                common = sum(a == b for a, b in zip(word, variant))
                if common >= len(variant) - 1:
                    return word
    return None


def remove_wake_word(text, detected):
    if not detected:
        return text.strip()
    pattern = r"^\s*" + re.escape(detected) + r"[\s,!.?;:-]*"
    return re.sub(pattern, "", text, count=1, flags=re.IGNORECASE).strip()


def process_command(command):
    if not command:
        return
    try:
        answer = _get_gateway().submit_voice(
            command,
            metadata={"session_id": "voice"},
        )
        if answer:
            speak(answer)
    except Exception as error:
        print("Ошибка voice gateway:", error)
        speak("Произошла ошибка.")


def main():
    active = False
    clear_audio_queue()
    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        blocksize=FRAME_SAMPLES,
        callback=audio_callback,
    ):
        while True:
            audio = record_utterance(
                timeout=DIALOGUE_TIMEOUT if active else None,
                end_silence_ms=WAKE_END_SILENCE_MS if not active else None,
            )
            if audio is None:
                active = False
                continue
            text = transcribe(audio)
            if not text:
                active = False
                continue
            if not active:
                detected = find_wake_word(text)
                if detected is None:
                    continue
                active = True
                command = remove_wake_word(text, detected)
                if not command:
                    speak("Да?")
                    continue
                process_command(command)
            else:
                process_command(text)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Акира остановлен.")
