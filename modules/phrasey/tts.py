import os

import requests


class TTS:
    def __init__(self):
        self.voices = {}
        try:
            for filename in os.listdir("data/voices"):
                if filename.endswith(".mp3"):
                    name = filename[:-4]
                    self.voices[name] = "data/voices/" + filename
        except FileNotFoundError:
            pass

    def get_voices(self):
        return list(self.voices.keys())

    def generate(self, text: str, speaker: str, language: str = "en"):
        url = "http://api.rk.conczin.net/v1/tts/xtts-v2"
        params = {
            "text": text,
            "language": language,
            "speaker": speaker,
            "file_format": "ogg",
            "cache": "false",
            "prepare_speakers": "0",
            "load_async": "false",
        }
        response = requests.post(url, params=params)
        return response.content
