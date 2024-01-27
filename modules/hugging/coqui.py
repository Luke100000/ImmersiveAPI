import io
import wave
from functools import cache

import numpy as np
from TTS.api import TTS


@cache
def get_model() -> TTS:
    return TTS("tts_models/multilingual/multi-dataset/xtts_v2")


def encode_as_wav(float_array, buffer, sample_rate=44100):
    pcm_data = (np.array(float_array) * 32767).astype(np.int16)

    with wave.open(buffer, "wb") as wave_file:
        wave_file.setnchannels(1)  # Mono audio
        wave_file.setsampwidth(2)  # 16-bit PCM
        wave_file.setframerate(sample_rate)
        wave_file.writeframes(pcm_data.tobytes())


@cache
def get_embedding(audio_path: str):
    tts = get_model()
    return tts.synthesizer.tts_model.get_conditioning_latents(audio_path=audio_path)


def generate_speech(
    text: str, speaker: str = None, language: str = "en", file_path: str = None
) -> bytes:
    tts = get_model()

    # Fetch embeddings
    gpt_cond_latent, speaker_embedding = get_embedding(speaker)

    # Generate speech
    wav = tts.synthesizer.tts_model.inference(
        text, language, gpt_cond_latent, speaker_embedding
    )["wav"]

    # Encode as WAV and optionally save to file
    if file_path is None:
        buffer = io.BytesIO()
        encode_as_wav(wav, buffer, tts.synthesizer.output_sample_rate)
        return buffer.getvalue()
    else:
        encode_as_wav(wav, file_path, tts.synthesizer.output_sample_rate)
