import os
import subprocess

from dotenv import load_dotenv
from elevenlabs import generate, Voice, voices, set_api_key

from modules.phrasey.utils import convert_to_ogg

load_dotenv()

set_api_key(os.getenv("ELEVENLABS_API_KEY"))

CHUNK_SIZE = 1024

voice_map = {}

for voice in voices():
    voice_map[voice.name.lower()] = voice.voice_id

voice_map = {"hardtack": "CvygltKK7uOYz0N8x8jy"}


def generate_elevenlabs_tts(text: str, voice_name: str, file: str):
    audio = generate(
        text=text,
        voice=Voice(voice_id=voice_map[voice_name]),
        model="eleven_multilingual_v2",
    )

    with open(file + ".mp3", "wb") as f:
        f.write(audio)

    convert_to_ogg(file + ".mp3", file)

    os.remove(file + ".mp3")
