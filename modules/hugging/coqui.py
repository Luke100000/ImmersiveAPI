import io
import wave
from functools import cache

import numpy as np
from TTS.api import TTS


@cache
def get_model() -> TTS:
    return TTS("tts_models/multilingual/multi-dataset/xtts_v2")


def encode_as_wav(float_array, sample_rate=44100):
    buffer = io.BytesIO()

    pcm_data = (np.array(float_array) * 32767).astype(np.int16)

    with wave.open(buffer, "wb") as wave_file:
        wave_file.setnchannels(1)  # Mono audio
        wave_file.setsampwidth(2)  # 16-bit PCM
        wave_file.setframerate(sample_rate)
        wave_file.writeframes(pcm_data.tobytes())

    return buffer.getvalue()


def generate_speech(text: str, speaker_wav: str, language: str = "en") -> bytes:
    tts = get_model()
    wav = tts.tts(
        text=text,
        speaker_wav="data/voices/pirate.mp3",
        language=language,
    )
    return encode_as_wav(wav, tts.synthesizer.output_sample_rate)
