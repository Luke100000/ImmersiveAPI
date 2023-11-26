import os
import urllib.request
from enum import Enum
from time import sleep

import requests
from dotenv import load_dotenv

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


voices: dict[str, Voice] = {}


def fetch_voices(url):
    response = requests.get(url, headers=headers)
    for voice in response.json():
        v = Voice(voice)
        voices[v.name] = v


# fetch_voices("https://api.play.ht/api/v2/voices")
fetch_voices("https://api.play.ht/api/v2/cloned-voices")


def request_tts(
    text: str, voice: Voice, emotion: Emotion = Emotion.NEUTRAL, speed: float = 1.0
):
    payload = {
        "text": text,
        "voice": voice.id,
        "quality": "high",
        "speed": speed,
        "output_format": "ogg",
        "sample_rate": "48000",
        "voice_engine": voice.voice_engine,
        "emotion": None
        if emotion == Emotion.NEUTRAL
        else (voice.gender + "_" + emotion.value),
    }

    response = requests.post(
        "https://api.play.ht/api/v2/tts", json=payload, headers=headers
    )

    print("Request", response.json())

    return response.json()["id"]


def download_tts(identifier, file):
    while True:
        response = requests.get(
            "https://api.play.ht/api/v2/tts/" + identifier, headers=headers
        )

        if "output" not in response.json():
            print("Failed to parse response", response.json())
            break

        print("Response", response.json())

        output = response.json()["output"]
        if output is not None:
            urllib.request.urlretrieve(output["url"], file)
            break
        else:
            print("Waiting for TTS to be generated...")
            sleep(5)
