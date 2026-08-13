import os
import tempfile
import threading

import sounddevice as sd
import soundfile as sf
from groq import Groq
from pynput import keyboard

SAMPLE_RATE = 16000
DURATION = 5

recording = False


def listen():
    global recording

    if recording:
        return

    recording = True

    try:
        print()
        print("АКИРА: слушаю...")
        
        audio = sd.rec(
            int(DURATION * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
        )

        sd.wait()

        print("АКИРА: распознаю...")

        with tempfile.NamedTemporaryFile(
            suffix=".wav",
            delete=False
        ) as f:
            filename = f.name

        sf.write(filename, audio, SAMPLE_RATE)

        try:
            api_key = os.environ.get("GROQ_API_KEY")

            if not api_key:
                raise RuntimeError("GROQ_API_KEY не найден.")

            client = Groq(api_key=api_key)

            with open(filename, "rb") as audio_file:
                transcription = client.audio.transcriptions.create(
                    file=(filename, audio_file.read()),
                    model="whisper-large-v3-turbo",
                    language="ru",
                )

            print("ТЫ:", transcription.text)

        finally:
            os.unlink(filename)

    except Exception as e:
        print("Ошибка голоса:", e)

    finally:
        recording = False


def main():
    print("АКИРА: голосовой режим запущен.")
    print("⌥ Space — начать разговор.")
    print("Ctrl+C — выйти.")

    with keyboard.GlobalHotKeys({
        "<alt>+<space>": listen
    }) as hotkeys:
        hotkeys.join()


if __name__ == "__main__":
    main()
