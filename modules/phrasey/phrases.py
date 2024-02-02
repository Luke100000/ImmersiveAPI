import json
import math
import os
import random
import shelve
import shutil
from collections import defaultdict
from functools import cache
from typing import List, Mapping

import numpy as np
from annoy import AnnoyIndex
from fastapi import FastAPI, HTTPException
from sentence_transformers import SentenceTransformer
from starlette.responses import FileResponse, Response
from tqdm.auto import tqdm

from modules.phrasey.engines.elvenlabs import (
    ElevenLabsEngine,
)
from modules.phrasey.engines.mystic import MysticEngine
from modules.phrasey.engines.playht import PlayHTEngine
from modules.phrasey.engines.xtts import XTTSEngine
from modules.phrasey.llm_helper import generate_phrase
from modules.phrasey.utils import hash_string, cosine_dist


@cache
def get_embedding_model():
    return SentenceTransformer("multi-qa-MiniLM-L6-cos-v1", device="cpu")


engines = [
    PlayHTEngine(),
    ElevenLabsEngine(),
    MysticEngine(),
    XTTSEngine(),
]

voices = {}
for engine in engines:
    for voice_name in engine.get_voices():
        voices[voice_name] = engine


class EventType:
    def __init__(self, identifier: str, weight: float):
        self.identifier = identifier
        self.weight = weight


types = [
    EventType("Task", 10),
    EventType("You", 8),
    EventType("Equipment", 4),
    EventType("Status", 6),
    EventType("Biome", 2),
    EventType("Light", 4),
    EventType("Weather", 4),
    EventType("Time", 4),
    EventType("Nearby", 4),
    EventType("Target", 8),
    EventType("Opponent", 8),
    EventType("OpponentEquipment", 3),
    EventType("OpponentStatus", 7),
]


@cache
def cached_embedd(sentence: str):
    return get_embedding_model().encode(sentence)


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
        embeddings = [
            cached_embedd(self.events[type.identifier])
            for type in types
            if type.identifier in self.events
        ]

        weights = np.asarray(
            [type.weight for type in types if type.identifier in self.events]
        )

        return np.sum(
            np.asarray(embeddings) * weights[:, None],
            axis=0,
        ) / np.sum(weights)

    def get_hash(self) -> str:
        return hash_string(self.get_full_str())

    def add_phrase(self, phrase):
        self.phrases.append(phrase)

    def get_importance(self, event_counts: Mapping[str, float]) -> float:
        """
        Count the total times phrases from this event have been used.
        Higher counts mean more commonly used.
        """
        importance = 0.0
        for type in self.events.values():
            importance += event_counts[type] if type in event_counts else 0
        return importance / len(self.events)


class Phrasey:
    def __init__(self, cache_dir: str, voice: str) -> None:
        super().__init__()

        self.voice = voice
        self.cache_dir = cache_dir
        self.dataset: List[Event] = []
        self.dataset_full: List[Event] = []
        self.annoy_index: AnnoyIndex = None

        os.makedirs(cache_dir, exist_ok=True)
        self.usage_counts = shelve.open(cache_dir + "/phrase_count.db")

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

    def generate_fake_dataset(self, count: int = 1000):
        # given a query field (task primarily), produce variation from the pool of other fields
        index = ("task",)
        phrases = defaultdict(lambda: defaultdict(list))
        for e in self.dataset_full:
            e_index = tuple((e.events[i] if i in e.events else "?") for i in index)
            for key, value in e.events.items():
                phrases[e_index][key].append(value)

        fake_events = []
        for e_index, e_phrases in phrases.items():
            for sample in range(int(math.ceil(count / len(phrases)))):
                fake_event = {}
                for type in types:
                    if type.identifier in e_phrases:
                        fake_event[type.identifier] = random.choice(
                            e_phrases[type.identifier]
                        )
                fake_events.append(Event(fake_event))

        return fake_events

    def clear(self):
        """
        Deletes all tts and phrases generated, but keeps the event descriptors.
        """
        for event_hash in os.listdir(self.cache_dir):
            if event_hash == "phrase_count.db":
                continue

            d = os.path.join(self.cache_dir, event_hash, "phrases")
            shutil.rmtree(d, ignore_errors=True)
            os.makedirs(d, exist_ok=True)

            d = os.path.join(self.cache_dir, event_hash, "tts")
            shutil.rmtree(d, ignore_errors=True)
            os.makedirs(d, exist_ok=True)

        self.usage_counts.clear()
        self.load()

    def generate(self, samples: int = 1, threshold: float = 1.0, dataset=None):
        if dataset is None:
            dataset = self.dataset_full

        # Count different events to construct importance
        event_counts = defaultdict(int)
        for event in self.dataset_full:
            h = event.get_hash()
            count = self.usage_counts[h] if h in self.usage_counts else 1
            for e in event.events.values():
                event_counts[e] += count

        # For every event, find the closest event
        distances = np.zeros(len(dataset))
        for i, event in tqdm(enumerate(dataset)):
            event_hash = event.get_hash()

            # The more it is used, the more important it is to generate another phrase
            usage_count = math.sqrt(
                self.usage_counts[event_hash] if event_hash in self.usage_counts else 1
            )

            # Find the closest event
            embedding = event.get_embedding()
            nn = self.annoy_index.get_nns_by_vector(embedding, 2)
            distance = (
                cosine_dist(self.dataset[nn[1]].get_embedding(), embedding) * 0.5 + 0.5
                if len(nn) > 1
                else 0
            )

            # Based on how well this even aligns with global usage, increase the importance
            importance = event.get_importance(event_counts)

            distances[i] = (
                distance / importance * (1 + len(event.phrases)) / usage_count
            )

        # Too unimportant
        distances = distances[distances < threshold]

        # Generate more phrases
        indices = np.argsort(-distances)
        for i in range(min(samples, len(indices))):
            event = dataset[indices[i]]
            event_hash = event.get_hash()
            self.save(event, event_hash)

            print("Generating phrase for event:")
            print(event.get_full_str())
            print("Score: ", distances[i])

            # Generate phrase
            phrase = generate_phrase(event.get_full())
            phrase_hash = hash_string(phrase)
            with open(f"{self.cache_dir}/{event_hash}/phrases/{phrase_hash}", "w") as f:
                f.write(phrase)

            print("Phrase: " + phrase)

            # Generate TTS
            output_file = f"{self.cache_dir}/{event_hash}/tts/{phrase_hash}.ogg"
            voices[self.voice].generate(phrase, self.voice, output_file)
            print("")

    def save(self, event: Event, event_hash: str = None):
        if event_hash is None:
            event_hash = event.get_hash()

        os.makedirs(f"{self.cache_dir}/{event_hash}/phrases", exist_ok=True)
        os.makedirs(f"{self.cache_dir}/{event_hash}/tts", exist_ok=True)

        with open(f"{self.cache_dir}/{event_hash}/events.json", "w") as f:
            json.dump(event.events, f, indent=4)

    def query(self, event: Event) -> (str, str):
        # Increase counter
        event_hash = event.get_hash()
        if event_hash not in self.usage_counts:
            self.usage_counts[event_hash] = 1
            self.save(event, event_hash)
        else:
            self.usage_counts[event_hash] += 1

        if len(self.dataset) == 0:
            return None, None

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


def load_phraseys():
    phraseys = {}

    for voice in voices.keys():
        phraseys[voice] = Phrasey("cache/voices/" + voice, voice)

    return phraseys


def initPhrasey(app: FastAPI):
    phraseys: dict[str, Phrasey] = load_phraseys()

    @app.get("/v1/phrasey/generate/{voice}")
    def get_hash(voice: str):
        if voice not in phraseys:
            raise HTTPException(status_code=404, detail="Voice not found")

        for sample in range(100):
            phraseys[voice].load()
            fake_dataset = (
                phraseys[voice].generate_fake_dataset() + phraseys[voice].dataset_full
            )
            phraseys[voice].generate(dataset=fake_dataset)

        return Response("Done")

    @app.get("/v1/phrasey/clear/{voice}")
    def get_hash(voice: str):
        if voice not in phraseys:
            raise HTTPException(status_code=404, detail="Voice not found")

        phraseys[voice].clear()

        return Response("Done")

    @app.get("/v1/phrasey/hash/{voice}")
    def get_hash(voice: str, events: str):
        if voice not in phraseys:
            raise HTTPException(status_code=404, detail="Voice not found")

        query_event = Event(json.loads(events))
        event_hash, phrase_hash = phraseys[voice].query(query_event)
        return Response("" if event_hash is None else (event_hash + "/" + phrase_hash))

    @app.get("/v1/phrasey/phrase/{voice}/{event_hash}/{phrase_hash}")
    def get_phrase(voice: str, event_hash: str, phrase_hash: str):
        if voice not in phraseys:
            raise HTTPException(status_code=404, detail="Voice not found")

        return Response(phraseys[voice].get_phrase(event_hash, phrase_hash))

    @app.get("/v1/phrasey/audio/{voice}/{event_hash}/{phrase_hash}")
    def get_audio(voice: str, event_hash: str, phrase_hash: str):
        if voice not in phraseys:
            raise HTTPException(status_code=404, detail="Voice not found")

        path = phraseys[voice].get_audio_path(event_hash, phrase_hash)
        return FileResponse(path, media_type="audio/ogg")

    @app.get("/v1/phrasey/voices")
    def get_audio():
        return [v for v in phraseys.keys()]
