import os
import tempfile

import sounddevice as sd
import soundfile as sf
from groq import Groq

SAMPLE_RATE = 16000
DURATION = 5

print()
print("АКИРА: слушаю 5 секунд...")
print("Говори сейчас.")

audio = sd.rec(
    int(DURATION * SAMPLE_RATE),
    samplerate=SAMPLE_RATE,
    channels=1,
    dtype="float32",
)

sd.wait()

print("АКИРА: записал. Распознаю...")

with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
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

    print()
    print("ТЫ:", transcription.text)

finally:
    os.unlink(filename)
