import json
import os.path
from functools import cache
from pathlib import Path

from piper import PiperVoice
from piper.download import get_voices, ensure_voice_exists

data_dir = Path("cache/piper")

# Voices that are either too specific or of low quality
blacklist = {"thorsten_emotional"}


@cache
def get_gender_lookup():
    if os.path.exists("data/piper_gender.json"):
        with open("data/piper_gender.json", "r") as f:
            return json.load(f)
    return {}


# Do not support low since those are 16 kHz and would need extra logic
quality = {"medium": 2, "high": 3}


@cache
def get_best_voices():
    data_dir.mkdir(parents=True, exist_ok=True)
    voices = get_voices(data_dir, True)
    best_voices = {}
    for info in voices.values():
        if info["quality"] in quality and (
            info["name"] not in best_voices
            or quality[info["quality"]] > quality[best_voices[info["name"]]["quality"]]
        ):
            best_voices[info["name"]] = info
    return best_voices


def speak(text: str, speaker: str):
    name, speaker_id = speaker.split(":", 1)
    voices = get_best_voices()

    # Download voice
    ensure_voice_exists(name, [data_dir], data_dir, voices)

    # Load voice
    voice = PiperVoice.load(
        data_dir / f"{voices[name]['key']}.onnx",
        data_dir / f"{voices[name]['key']}.onnx.json",
    )

    # Generate audio
    audio_stream = voice.synthesize_stream_raw(
        text, speaker_id=None if speaker_id == "-1" else int(speaker_id)
    )
    for audio_bytes in audio_stream:
        yield audio_bytes
