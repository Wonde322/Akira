import os
import re
import time
import tempfile
import collections
import queue
import threading

import numpy as np
import sounddevice as sd
import soundfile as sf
import webrtcvad

from brain import ask
from config import create_groq_client
from permissions import deny_all, set_confirmation_provider


set_confirmation_provider(deny_all)


SAMPLE_RATE = 16000
FRAME_MS = 30
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000

VAD_MODE = 1

END_SILENCE_MS = 1200
PRE_ROLL_MS = 450
MAX_UTTERANCE_MS = 15000

# После ответа Акира остаётся в диалоге столько секунд
# даже если пользователь молчит.
DIALOGUE_TIMEOUT = 8


vad = webrtcvad.Vad(VAD_MODE)
client = None


def _ensure_client():
    global client

    if client is None:
        client = create_groq_client()

    return client

audio_queue = queue.Queue()

speaking = False
speak_proc = None
_speak_lock = threading.Lock()


WAKE_VARIANTS = {
    "акира",
    "кира",
    "акера",
    "акиро",
    "акыра",
    "акираа",
    "акирах",
    "акйра",
    "акирая",
}

# Известные whisper-галлюцинации на тишине/шуме. Такое никогда не должно
# превращаться в пользовательское сообщение.
_HALLUCINATIONS = (
    "продолжение следует",
    "если понадобится продолжить или есть вопросы",
    "дай знать если понадобится продолжить",
    "большое спасибо за просмотр",
    "спасибо за просмотр",
    "подпишись на канал",
    "нажми подписаться",
    "не забывайте подписываться",
)


def _is_hallucination(text):
    """True, если текст похож на типичную whisper-галлюцинацию."""
    if not text:
        return False

    normalized = text.lower().replace("ё", "е")

    for phrase in _HALLUCINATIONS:
        if phrase in normalized:
            return True

    return False


def speak(text):
    """Акира говорит и в это время полностью игнорирует микрофон."""
    global speaking

    if not text:
        return

    speaking = True

    # Удаляем всё, что могло попасть в очередь до начала ответа.
    clear_audio_queue()

    print("АКИРА:", text)

    try:
        import subprocess

        from config import TTS_VOICE

        proc = subprocess.Popen(
            ["say", "-v", TTS_VOICE, text],
        )

        with _speak_lock:
            global speak_proc
            speak_proc = proc

        proc.wait()

        with _speak_lock:
            speak_proc = None
    finally:
        # После речи даём микрофону немного успокоиться.
        clear_audio_queue()
        speaking = False


def stop_speaking():
    """Прерывает текущую озвучку (если она идёт)."""
    with _speak_lock:
        proc = speak_proc

    if proc is not None:
        proc.terminate()


def audio_callback(indata, frames, time_info, status):
    if status:
        print("Audio:", status)

    if speaking:
        return

    audio_queue.put(indata[:, 0].copy())


def is_speech(frame):
    pcm = np.asarray(
        frame * 32767,
        dtype=np.int16
    )

    return vad.is_speech(
        pcm.tobytes(),
        SAMPLE_RATE
    )


def clear_audio_queue():
    while True:
        try:
            audio_queue.get_nowait()
        except queue.Empty:
            break


def record_utterance(timeout=None, cancel_event=None):
    """
    Записывает одну полноценную фразу:
    начало речи → вся фраза → пауза.
    """

    pre_roll = collections.deque(
        maxlen=PRE_ROLL_MS // FRAME_MS
    )

    silence_limit = END_SILENCE_MS // FRAME_MS
    max_frames = MAX_UTTERANCE_MS // FRAME_MS

    recording = False
    frames = []
    silence_count = 0

    started_at = time.time()

    while True:

        if cancel_event is not None and cancel_event.is_set():
            return None

        if timeout is not None:
            if time.time() - started_at > timeout:
                return None

        try:
            frame = audio_queue.get(
                timeout=0.2
            )
        except queue.Empty:
            continue

        speech = is_speech(frame)

        if not recording:

            pre_roll.append(frame)

            if speech:
                recording = True

                frames.extend(
                    list(pre_roll)
                )

                frames.append(frame)
                silence_count = 0

        else:

            frames.append(frame)

            if speech:
                silence_count = 0
            else:
                silence_count += 1

            if silence_count >= silence_limit:
                break

            if len(frames) >= max_frames:
                break

    if not frames:
        return None

    return np.concatenate(frames)


def transcribe(audio):
    with tempfile.NamedTemporaryFile(
        suffix=".wav",
        delete=False
    ) as f:

        filename = f.name

    try:

        sf.write(
            filename,
            audio,
            SAMPLE_RATE
        )

        with open(
            filename,
            "rb"
        ) as audio_file:

            result = _ensure_client().audio.transcriptions.create(
                file=(
                    filename,
                    audio_file.read()
                ),
                model="whisper-large-v3",
                language="ru",
                temperature=0,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
                prompt=(
                    "Русская речь пользователя. "
                    "Имя голосового ассистента: Акира. "
                    "Возможные варианты имени: Акира, Кира, Акера, Акиро. "
                    "Не придумывай текст, если речи нет."
                ),
            )

        text = (result.text or "").strip()

        if _is_hallucination(text):
            return ""

        # Отбрасываем явные галлюцинации/тишину.
        segments = getattr(result, "segments", None) or []

        if segments:
            no_speech = max(
                float(getattr(seg, "no_speech_prob", 0))
                for seg in segments
            )

            avg_logprob = min(
                float(getattr(seg, "avg_logprob", 0))
                for seg in segments
            )

            print(
                f"Whisper confidence: "
                f"no_speech={no_speech:.2f}, "
                f"avg_logprob={avg_logprob:.2f}"
            )

            if no_speech > 0.70:
                return ""

            if avg_logprob < -1.2:
                return ""

        return text

    finally:
        os.unlink(filename)


def find_wake_word(text):
    """
    Возвращает найденный вариант имени
    или None.
    """

    normalized = (
        text
        .lower()
        .replace("ё", "е")
    )

    words = re.findall(
        r"[а-яa-z]+",
        normalized
    )

    for word in words:

        if word in WAKE_VARIANTS:
            return word

        # Небольшая терпимость к ошибкам Whisper.
        if len(word) >= 4:

            for variant in WAKE_VARIANTS:

                if len(variant) < 4:
                    continue

                common = sum(
                    1
                    for a, b in zip(
                        word,
                        variant
                    )
                    if a == b
                )

                if common >= len(variant) - 1:
                    return word

    return None


def remove_wake_word(text, detected):
    """
    Убирает имя из начала команды.

    Например:
    'Акира, включи музыку'
    →
    'включи музыку'
    """

    if not detected:
        return text.strip()

    pattern = (
        r"^\s*"
        + re.escape(detected)
        + r"[\s,!.?;:-]*"
    )

    return re.sub(
        pattern,
        "",
        text,
        count=1,
        flags=re.IGNORECASE
    ).strip()


def process_command(command):
    if not command:
        return

    print()
    print("КОМАНДА:", command)
    print()

    try:
        answer = ask(command, session_id="voice")

        if answer:
            speak(answer)

    except Exception as e:
        print("Ошибка brain.py:", e)
        speak("Произошла ошибка.")


def main():

    print()
    print("==============================")
    print("        AKIRA DIALOGUE")
    print("==============================")
    print()
    print("Постоянное прослушивание: ВКЛ")
    print("Wake word: Акира / Кира")
    print("Ctrl+C — остановить.")
    print()

    active = False
    last_activity = 0

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        blocksize=FRAME_SAMPLES,
        callback=audio_callback,
    ):

        while True:

            # ==================================
            # РЕЖИМ ОЖИДАНИЯ
            # ==================================

            if not active:

                print(
                    "Жду Акиру...",
                    end="\r",
                    flush=True
                )

                audio = record_utterance()

                if audio is None:
                    continue

                try:
                    text = transcribe(audio)
                except Exception as e:
                    print(
                        "\nОшибка Whisper:",
                        e
                    )
                    continue

                if not text:
                    continue

                print(
                    "\nУслышал:",
                    text
                )

                detected = find_wake_word(
                    text
                )

                if detected is None:
                    continue

                print(
                    f">>> АКИРА ПРОСНУЛСЯ "
                    f"({detected}) <<<"
                )

                active = True
                last_activity = time.time()

                # Если команда была сразу после имени:
                command = remove_wake_word(
                    text,
                    detected
                )

                if command:
                    process_command(
                        command
                    )
                    last_activity = time.time()

                else:
                    clear_audio_queue()
                    speak("Да?")
                    last_activity = time.time()

                continue

            # ==================================
            # АКТИВНЫЙ ДИАЛОГ
            # ==================================

            print(
                "Диалог активен...",
                end="\r",
                flush=True
            )

            audio = record_utterance(
                timeout=DIALOGUE_TIMEOUT
            )

            if audio is None:
                active = False
                print(
                    "\nДиалог завершён."
                )
                continue

            try:
                text = transcribe(audio)
            except Exception as e:
                print(
                    "\nОшибка Whisper:",
                    e
                )
                continue

            if not text:
                continue

            print(
                "\nУслышал:",
                text
            )

            process_command(text)

            last_activity = time.time()


if __name__ == "__main__":

    try:
        main()

    except KeyboardInterrupt:
        print()
        print("Акира остановлен.")
