import json
import math
import os
import random
import shelve
from collections import defaultdict
from typing import List

import numpy as np
from annoy import AnnoyIndex
from fastapi import FastAPI, HTTPException
from sentence_transformers import SentenceTransformer
from starlette.responses import FileResponse, Response

from modules.phrasey.openai_helper import generate_phrase
from modules.phrasey.playht import voices, request_tts, download_tts, Voice
from modules.phrasey.utils import hash_string, cosine_dist

model = SentenceTransformer("multi-qa-MiniLM-L6-cos-v1", device="cpu")


class EventType:
    def __init__(self, identifier: str, weight: float):
        self.identifier = identifier
        self.weight = weight


types = [
    EventType("Task", 1.0),
    EventType("You", 1.0),
    EventType("Equipment", 1.0),
    EventType("Status", 1.0),
    EventType("Opponent", 1.0),
    EventType("OpponentEquipment", 1.0),
    EventType("OpponentStatus", 1.0),
    EventType("Biome", 1.0),
    EventType("Time", 1.0),
    EventType("Nearby", 1.0),
    EventType("First", 1.0),
    EventType("Second", 1.0),
]


class Event:
    def __init__(self, events: dict):
        self.events: dict[str, str] = events
        self.phrases = []

    def get_full(self) -> List[str]:
        full = []
        for type in types:
            if type.identifier in self.events:
                full.append(self.events[type.identifier])

        return full

    def get_full_str(self) -> str:
        return "\n".join(self.get_full())

    def get_embedding(self) -> np.ndarray:
        return model.encode(self.get_full_str())

    def get_hash(self) -> str:
        return hash_string(self.get_full_str())

    def add_phrase(self, phrase):
        self.phrases.append(phrase)

    def get_importance(self, event_count):
        importance = 0.0
        for type in self.events.values():
            importance += event_count[type]
        return importance / (len(self.phrases) + 0.1)


class Phrasey:
    def __init__(self, cache_dir: str, voice: Voice) -> None:
        super().__init__()

        self.voice = voice
        self.cache_dir = cache_dir
        self.dataset: List[Event] = []
        self.dataset_full: List[Event] = []
        self.annoy_index: AnnoyIndex = None

        self.counts = shelve.open(cache_dir + "/phrase_count.db")

        self.load()

    def load(self):
        vector_size = 384
        self.dataset = []
        self.dataset_full = []
        self.annoy_index = AnnoyIndex(vector_size, "angular")

        for event_hash in os.listdir(self.cache_dir):
            if event_hash == "phrase_count.db":
                continue

            subdir_path = os.path.join(self.cache_dir, event_hash)

            # Load event descriptor
            events_file = os.path.join(subdir_path, "events.json")
            with open(events_file, "r") as f:
                event = Event(json.load(f))

            # Load all generated phrases
            phrases_dir = os.path.join(subdir_path, "tts")
            for phrase in os.listdir(phrases_dir):
                event.add_phrase(phrase.replace(".ogg", ""))

            # Add to dataset
            if len(event.phrases) > 0:
                vector = event.get_embedding()
                self.annoy_index.add_item(len(self.dataset), vector)
                self.dataset.append(event)
            self.dataset_full.append(event)

        # Build lookup
        self.annoy_index.build(n_trees=10, n_jobs=2)

    def generate(self, samples: int = 10):
        event_count = defaultdict(int)

        # Count different events to construct importance
        for event in self.dataset_full:
            for e in event.events.values():
                event_count[e] += 1

        # Normalize event importance
        counts = [v for v in event_count.values()]
        max_count = 0 if len(counts) == 0 else max(counts)
        for key in event_count:
            event_count[key] /= max_count

        # For every event, find the closest event
        scores = np.zeros(len(self.dataset_full))
        for i, event in enumerate(self.dataset_full):
            embedding = event.get_embedding()
            nn = self.annoy_index.get_nns_by_vector(embedding, 2)
            if len(nn) > 1:
                distance = max(
                    0.0, cosine_dist(self.dataset[nn[1]].get_embedding(), embedding)
                )
                scores[i] = (
                    distance
                    * event.get_importance(event_count)
                    * math.sqrt(self.counts[event.get_hash()] or 1)
                )
            else:
                scores[i] = event.get_importance(event_count) * math.sqrt(
                    self.counts[event.get_hash()] or 1
                )

        # Generate more phrases
        indices = np.argsort(-scores)
        for i in range(min(samples, len(self.dataset_full))):
            if scores[i] > 0.01:
                event = self.dataset_full[indices[i]]
                event_hash = event.get_hash()

                print("Generating phrase for event:")
                print(event.get_full_str())
                print("Score: ", scores[i])

                # Generate phrase
                phrase = generate_phrase(event.get_full())
                phrase_hash = hash_string(phrase)
                with open(
                    f"{self.cache_dir}/{event_hash}/phrases/{phrase_hash}", "w"
                ) as f:
                    f.write(phrase)

                print("Phrase: " + phrase)

                # Generate TTS
                identifier = request_tts(phrase, self.voice)
                print("Play.ht identifier: " + identifier)
                download_tts(
                    identifier, f"{self.cache_dir}/{event_hash}/tts/{phrase_hash}.ogg"
                )
                print("")

    def save(self, event_hash: str, event: Event):
        os.makedirs(f"{self.cache_dir}/{event_hash}/phrases", exist_ok=True)
        os.makedirs(f"{self.cache_dir}/{event_hash}/tts", exist_ok=True)

        with open(f"{self.cache_dir}/{event_hash}/events.json", "w") as f:
            json.dump(event.events, f, indent=4)

    def query(self, event: Event) -> (str, str):
        # Increase counter
        event_hash = event.get_hash()
        if event_hash not in self.counts:
            self.counts[event_hash] = 1
            self.save(event_hash, event)
        else:
            self.counts[event_hash] += 1

        # Find the closest event
        index = self.annoy_index.get_nns_by_vector(event.get_embedding(), 1)[0]
        closest_event = self.dataset[index]
        phrases = closest_event.phrases
        return closest_event.get_hash(), phrases[random.randint(0, len(phrases) - 1)]

    def get_phrase(self, event_hash, phrase_hash):
        with open(f"{self.cache_dir}/{event_hash}/phrases/{phrase_hash}", "r") as f:
            return f.read()

    def get_audio_path(self, event_hash, phrase_hash):
        return f"{self.cache_dir}/{event_hash}/tts/{phrase_hash}.ogg"


def initPhrasey(app: FastAPI):
    phraseys: dict[str, Phrasey] = {
        voice.name: Phrasey("cache/" + voice.name, voice) for voice in voices.values()
    }

    @app.get("/v1/phrasey/hash/{voice}")
    def get_hash(voice: str, events: str):
        if voice not in voices:
            raise HTTPException(status_code=404, detail="Voice not found")

        query_event = Event(json.loads(events))
        event_hash, phrase_hash = phraseys[voice].query(query_event)
        return Response("" if event_hash is None else (event_hash + "/" + phrase_hash))

    @app.get("/v1/phrasey/phrase/{voice}/{event_hash}/{phrase_hash}")
    def get_phrase(voice: str, event_hash: str, phrase_hash: str):
        if voice not in voices:
            raise HTTPException(status_code=404, detail="Voice not found")

        return Response(phraseys[voice].get_phrase(event_hash, phrase_hash))

    @app.get("/v1/phrasey/audio/{voice}/{event_hash}/{phrase_hash}")
    def get_audio(voice: str, event_hash: str, phrase_hash: str):
        if voice not in voices:
            raise HTTPException(status_code=404, detail="Voice not found")

        path = phraseys[voice].get_audio_path(event_hash, phrase_hash)
        return FileResponse(path, media_type="audio/ogg")

    @app.get("/v1/phrasey/voices")
    def get_audio():
        return [v.name for v in voices.values()]


def main():
    print("Training phrasey")
    phrasey = Phrasey("../../cache/hardtack", voices["hardtack"])
    phrasey.generate(1)


if __name__ == "__main__":
    main()
