import os

from dotenv import load_dotenv
from elevenlabs import generate, Voice, voices, set_api_key

from modules.phrasey.tts import TTS
from modules.phrasey.utils import convert_to_ogg

load_dotenv()

key = os.getenv("ELEVENLABS_API_KEY")
if key:
    set_api_key(key)

CHUNK_SIZE = 1024

voice_map = {}


def populate_voices():
    for voice in voices():
        voice_map[voice.name.lower()] = voice.voice_id


populate_voices()


def generate_elevenlabs_tts(text: str, voice_name: str, file: str):
    audio = generate(
        text=text,
        voice=Voice(voice_id=voice_map[voice_name]),
    )

    with open(file + ".mp3", "wb") as f:
        f.write(audio)

    convert_to_ogg(file + ".mp3", file)

    os.remove(file + ".mp3")


class ElevenLabsEngine(TTS):
    def get_voices(self):
        return ["11_" + v for v in voice_map.keys()]

    def generate(self, text: str, voice: str, file: str):
        generate_elevenlabs_tts(text, voice[3:], file)
