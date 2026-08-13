import os
import re
import queue
import tempfile
import collections

import numpy as np
import sounddevice as sd
import soundfile as sf
import webrtcvad
from groq import Groq

SAMPLE_RATE = 16000
FRAME_MS = 30
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000

VAD_MODE = 1
END_SILENCE_MS = 1200
PRE_ROLL_MS = 450
MAX_UTTERANCE_MS = 15000

vad = webrtcvad.Vad(VAD_MODE)
client = Groq(api_key=os.environ["GROQ_API_KEY"])

audio_queue = queue.Queue()


def callback(indata, frames, time_info, status):
    if status:
        print("Audio:", status)

    audio_queue.put(indata[:, 0].copy())


def is_speech(frame):
    pcm = np.asarray(frame * 32767, dtype=np.int16)
    return vad.is_speech(pcm.tobytes(), SAMPLE_RATE)


def record_utterance():
    pre_roll = collections.deque(
        maxlen=PRE_ROLL_MS // FRAME_MS
    )

    silence_limit = END_SILENCE_MS // FRAME_MS
    max_frames = MAX_UTTERANCE_MS // FRAME_MS

    recording = False
    frames = []
    silence_count = 0

    print("Слушаю...")

    while True:
        frame = audio_queue.get()

        speech = is_speech(frame)

        if not recording:
            pre_roll.append(frame)

            if speech:
                recording = True
                frames.extend(pre_roll)
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
        sf.write(filename, audio, SAMPLE_RATE)

        with open(filename, "rb") as audio_file:
            result = client.audio.transcriptions.create(
                file=(filename, audio_file.read()),
                model="whisper-large-v3-turbo",
                language="ru",
                temperature=0,
                prompt="Имя голосового ассистента: Акира. Возможные варианты распознавания имени: Акира, Кира, Акера, Акиро.",
            )

        return result.text.strip()

    finally:
        os.unlink(filename)


def main():
    print()
    print("==============================")
    print("     AKIRA STREAM VAD TEST")
    print("==============================")
    print()
    print("Используется встроенный микрофон Mac.")
    print("Говори обычными фразами.")
    print("Ctrl+C — остановить.")
    print()

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        blocksize=FRAME_SAMPLES,
        callback=callback,
    ):
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
                print("Ошибка:", e)
                continue

            if text:
                print("Услышал:", text)

                normalized_text = text.lower().replace("ё", "е")

                # Отдельные слова проверяем независимо,
                # чтобы "Кира" тоже считалось обращением к Акире.
                words = re.findall(r"[а-яa-z]+", normalized_text)

                wake_variants = {
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

                wake_detected = False
                detected_name = None

                for word in words:
                    if word in wake_variants:
                        wake_detected = True
                        detected_name = word
                        break

                    # Whisper иногда добавляет/теряет одну букву.
                    if len(word) >= 4:
                        for variant in wake_variants:
                            if len(variant) >= 4:
                                common = sum(
                                    1 for a, b in zip(word, variant)
                                    if a == b
                                )
                                if common >= len(variant) - 1:
                                    wake_detected = True
                                    detected_name = word
                                    break

                    if wake_detected:
                        break

                if wake_detected:
                    print()
                    print(f">>> АКИРА ПРОСНУЛСЯ <<<  (услышал: {detected_name})")
                    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nОстановлено.")
