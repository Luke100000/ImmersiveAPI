import os
import urllib.request
from enum import Enum
from time import sleep

import requests
from dotenv import load_dotenv

from modules.phrasey.tts import TTS
from modules.phrasey.utils import convert_to_ogg

load_dotenv()
headers = {
    "accept": "application/json",
    "AUTHORIZATION": os.getenv("PLAY_HT_SECRET_KEY"),
    "X-USER-ID": os.getenv("PLAY_HT_USER_ID"),
}


class Voice:
    def __init__(self, json: dict):
        self.name = json["name"].lower()
        self.id = json["id"]
        self.gender = json["gender"]
        self.voice_engine = json["voice_engine"]

    def __str__(self):
        return self.name

    def __repr__(self):
        return self.name


class Emotion(Enum):
    NEUTRAL = "neutral"
    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    FEARFUL = "fearful"
    DISGUSTED = "disgust"
    SURPRISED = "surprised"


voice_map: dict[str, Voice] = {}


def fetch_voices(url):
    response = requests.get(url, headers=headers)
    for voice in response.json():
        v = Voice(voice)
        voice_map[v.name] = v


if os.getenv("PLAY_HT_SECRET_KEY"):
    # fetch_voices("https://api.play.ht/api/v2/voices")
    fetch_voices("https://api.play.ht/api/v2/cloned-voices")


def request_tts(
    text: str, voice_name: str, emotion: Emotion = Emotion.NEUTRAL, speed: float = 1.0
):
    voice = voice_map[voice_name]

    payload = {
        "text": text,
        "voice": voice.id,
        "quality": "high",
        "speed": speed,
        "output_format": "wav",
        "sample_rate": "48000",
        "voice_engine": voice.voice_engine,
        "emotion": None
        if emotion == Emotion.NEUTRAL
        else (voice.gender + "_" + emotion.value),
    }

    response = requests.post(
        "https://api.play.ht/api/v2/tts", json=payload, headers=headers
    )

    return response.json()["id"]


def download_tts(identifier, file):
    while True:
        response = requests.get(
            "https://api.play.ht/api/v2/tts/" + identifier, headers=headers
        )

        if "output" not in response.json():
            print("Failed to parse response", response.json())
            break

        output = response.json()["output"]
        if output is not None:
            urllib.request.urlretrieve(output["url"], file + ".wav")
            convert_to_ogg(file + ".wav", file)
            os.remove(file + ".wav")
            break
        else:
            print("Waiting for TTS to be generated...")
            sleep(5)


class PlayHTEngine(TTS):
    def get_voices(self):
        return ["ht_" + v for v in voice_map.keys()]

    def generate(self, text: str, voice: str, file: str):
        identifier = request_tts(text, voice[3:])
        download_tts(identifier, file)
