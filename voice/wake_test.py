import os
import tempfile
import time

import numpy as np
import sounddevice as sd
import soundfile as sf
from groq import Groq

SAMPLE_RATE = 16000
CHUNK_SECONDS = 2
THRESHOLD = 0.012

client = Groq(api_key=os.environ["GROQ_API_KEY"])


def record_chunk():
    audio = sd.rec(
        int(CHUNK_SECONDS * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
    )
    sd.wait()
    return audio.flatten()


def transcribe(audio):
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        filename = f.name

    try:
        sf.write(filename, audio, SAMPLE_RATE)

        with open(filename, "rb") as audio_file:
            result = client.audio.transcriptions.create(
                file=(filename, audio_file.read()),
                model="whisper-large-v3-turbo",
                language="ru",
            )

        return result.text.strip()

    finally:
        os.unlink(filename)


def main():
    print()
    print("================================")
    print("        AKIRA WAKE TEST")
    print("================================")
    print()
    print("Микрофон слушает постоянно.")
    print('Скажи: "Акира"')
    print("Ctrl+C — остановить.")
    print()

    while True:
        audio = record_chunk()

        # Определяем, есть ли вообще звук.
        volume = np.sqrt(np.mean(audio ** 2))

        if volume < THRESHOLD:
            continue

        print("Речь обнаружена...")

        try:
            text = transcribe(audio)
        except Exception as e:
            print("Ошибка распознавания:", e)
            continue

        if not text:
            continue

        print("Услышал:", text)

        import re

        normalized = text.lower().replace("ё", "е")
        normalized = re.sub(r"[^а-яa-z]", "", normalized)

        wake_words = (
            "акира",
            "акера",
            "акиро",
            "акираа",
        )

        print("Нормализовано:", repr(normalized))

        if any(word in normalized for word in wake_words):
            print()
            print(">>> АКИРА ПРОСНУЛСЯ <<<")
            print()

        time.sleep(0.1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nОстановлено.")
