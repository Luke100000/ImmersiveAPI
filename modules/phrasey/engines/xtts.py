import os

from modules.hugging.coqui import generate_speech
from common.worker import get_primary_executor
from modules.phrasey.tts import TTS
from modules.phrasey.utils import convert_to_ogg

# Collect all voices
voices = {}
try:
    for filename in os.listdir("data/voices"):
        if filename.endswith(".mp3"):
            name = filename[:-4]
            voices[name] = "data/voices/" + filename
except FileNotFoundError:
    pass


class XTTSEngine(TTS):
    def get_voices(self):
        return ["xt_" + v for v in voices.keys()]

    def generate(self, text: str, voice: str, file: str):
        get_primary_executor().submit(
            1,
            generate_speech,
            text,
            speaker_wav="data/voices/" + voice[3:] + ".mp3",
            file_path=file + ".wav",
        ).result()
        convert_to_ogg(file + ".wav", file)
        os.remove(file + ".wav")
