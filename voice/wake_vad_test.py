import os
import re
import tempfile
import collections

import numpy as np
import sounddevice as sd
import soundfile as sf
import webrtcvad
from groq import Groq

SAMPLE_RATE = 16000

# 30 мс — один из поддерживаемых WebRTC VAD размеров кадра.
FRAME_MS = 30
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000

# Насколько агрессивно отсекаем шум.
# 0 = мягко, 3 = очень агрессивно.
VAD_MODE = 2

# Сколько тишины ждём после окончания речи.
END_SILENCE_MS = 750

# Небольшой запас до начала речи, чтобы не съедать первые слова.
PRE_ROLL_MS = 300

# Максимальная длина одной реплики.
MAX_UTTERANCE_MS = 12000

vad = webrtcvad.Vad(VAD_MODE)
client = Groq(api_key=os.environ["GROQ_API_KEY"])


def frame_is_speech(frame):
    pcm = np.asarray(frame * 32767, dtype=np.int16)
    return vad.is_speech(pcm.tobytes(), SAMPLE_RATE)


def record_utterance():
    pre_roll_frames = PRE_ROLL_MS // FRAME_MS
    silence_frames_needed = END_SILENCE_MS // FRAME_MS
    max_frames = MAX_UTTERANCE_MS // FRAME_MS

    buffer = collections.deque(maxlen=pre_roll_frames)

    recording = False
    speech_frames = []
    silence_count = 0

    print("Слушаю...")

    while True:
        audio = sd.rec(
            FRAME_SAMPLES,
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
        )
        sd.wait()

        frame = audio[:, 0]
        speech = frame_is_speech(frame)

        if not recording:
            buffer.append(frame.copy())

            if speech:
                recording = True
                speech_frames.extend(list(buffer))
                speech_frames.append(frame.copy())
                silence_count = 0

        else:
            speech_frames.append(frame.copy())

            if speech:
                silence_count = 0
            else:
                silence_count += 1

            if silence_count >= silence_frames_needed:
                break

            if len(speech_frames) >= max_frames:
                break

    if not speech_frames:
        return None

    return np.concatenate(speech_frames)


def transcribe(audio):
    with tempfile.NamedTemporaryFile(
        suffix=".wav",
        delete=False
    ) as f:
        filename = f.name

    try:
        sf.write(filename, audio, SAMPLE_RATE)

        with open(filename, "rb") as audio_file:
            result = client.audio.transcriptions.create(
                file=(filename, audio_file.read()),
                model="whisper-large-v3-turbo",
                language="ru",
                temperature=0,
            )

        return result.text.strip()

    finally:
        os.unlink(filename)


def main():
    print()
    print("==============================")
    print("       AKIRA VAD TEST")
    print("==============================")
    print()
    print("Говори обычными фразами.")
    print("Я записываю от начала речи до конца паузы.")
    print("Ctrl+C — остановить.")
    print()

    while True:
        audio = record_utterance()

        if audio is None:
            continue

        duration = len(audio) / SAMPLE_RATE
        print(f"Записано: {duration:.1f} сек.")
        print("Распознаю...")

        try:
            text = transcribe(audio)
        except Exception as e:
            print("Ошибка распознавания:", e)
            continue

        if not text:
            continue

        print("Услышал:", text)

        normalized = text.lower().replace("ё", "е")
        normalized = re.sub(r"[^а-яa-z]", "", normalized)

        wake_words = (
            "акира",
            "акера",
            "акиро",
            "акираа",
        )

        if any(word in normalized for word in wake_words):
            print()
            print(">>> АКИРА ПРОСНУЛСЯ <<<")
            print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nОстановлено.")
