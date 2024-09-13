import base64
import json
import logging
import os
import random
import threading
import time
from queue import PriorityQueue
from typing import Optional, Union

import audioread
import chromadb
import numpy as np
from fastapi import HTTPException

from main import Configurator
from modules.phrasey.environments.environment import Environment, JsonFormat
from modules.phrasey.environments.minecraft import MinecraftEnvironment
from modules.phrasey.llm import generate_phrases
from modules.phrasey.tts import TTS

logger = logging.getLogger(__name__)


def load_json(file: str) -> Union[dict, list]:
    with open(file, "r") as f:
        return json.load(f)


class Task:
    def __init__(self, loss: float, prompt: str, params: dict[str, str]) -> None:
        self.loss = loss
        self.prompt = prompt
        self.params = params

    def __lt__(self, other):
        return self.loss < other.loss


class Phrasey:
    engines = [TTS()]

    def __init__(self, save_dir: str, environment: Environment) -> None:
        super().__init__()

        self.voices = {}
        for engine in self.engines:
            for voice in engine.voices:
                self.voices[voice] = engine

        self.cache_dir = save_dir
        os.makedirs(save_dir, exist_ok=True)

        self.environment = environment

        self.max_samples = 10

        self.client = chromadb.HttpClient(
            host=os.getenv("CHROMA_HOST", "localhost"),
            port=os.getenv("CHROMA_PORT", 8000),
        )
        self.collection = self.client.get_or_create_collection("phrasey")
        self.queue = PriorityQueue()

        self.thread = threading.Thread(target=self._generator, daemon=True)
        self.thread.start()

        print("Validating database...")
        self.validate()
        print("Validated!")

    def _generator(self):
        while True:
            task = self.queue.get()
            logger.info(
                f"Generating phrase for {self.environment} with loss {task.loss}. {self.queue.qsize()} remaining."
            )
            self.generate(task.prompt, task.params)

    def generate(self, prompt: str, params: dict[str, str]):
        dialogue = self.environment.get_json_format(params) == JsonFormat.DIALOGUE
        phrases = generate_phrases(prompt, dialogue=dialogue)

        for sample in [phrases] if dialogue else [[p] for p in phrases]:
            self.generate_phrase(prompt, params, sample)

    @staticmethod
    def get_identifier() -> str:
        index = int(time.time() * 1000)
        max_index = 10_000
        directory_index = index // max_index
        phrase_index = index % max_index
        return f"{directory_index}/{phrase_index}"

    def generate_phrase(
        self,
        prompt: str,
        params: dict[str, str],
        phrases: list[str],
        identifier: str = None,
    ):
        if identifier is None:
            identifier = self.get_identifier()

        os.makedirs(f"{self.cache_dir}/{identifier}", exist_ok=True)

        with open(f"{self.cache_dir}/{identifier}/phrases.json", "w") as f:
            json.dump(phrases, f, indent=4)

        with open(f"{self.cache_dir}/{identifier}/params.json", "w") as f:
            json.dump(params, f, indent=4)

        with open(f"{self.cache_dir}/{identifier}/prompt.txt", "w") as f:
            f.write(prompt)

        # Generate audios
        voices = self.environment.get_valid_voices(params)
        self.populate_audios(identifier, phrases, voices)

        # Add to database
        self.collection.upsert(
            documents=prompt,
            metadatas=params,
            ids=identifier,
        )

    def populate_audios(
        self, identifier: str, phrases: list[str], voices: list[str]
    ) -> int:
        count = 0
        for voice in voices:
            for i, phrase in enumerate(phrases):
                file = f"{self.cache_dir}/{identifier}/{voice}/{i}.ogg"
                if not os.path.exists(file):
                    os.makedirs(
                        f"{self.cache_dir}/{identifier}/{voice}",
                        exist_ok=True,
                    )
                    audio = self.voices[voice].generate(phrase, "Marcos Rudaski")
                    with open(file, "wb") as f:
                        f.write(audio)
                    count += 1
        return count

    def query(
        self, params: dict[str, str], blacklist: set[str] = None
    ) -> Optional[str]:
        try:
            # Construct prompt, filter, and valid voices for this query
            prompt = self.environment.get_prompt(params)
            tags = self.environment.get_filter(params)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

        for p in tags:
            if p not in params:
                params[p] = "None"

        results = self.collection.query(
            query_texts=[prompt],
            where={"$and": [{p: params[p]} for p in tags]},
            n_results=self.max_samples,
        )

        samples = len(results["ids"][0])
        distances = np.asarray(results["distances"][0])
        print("distances", distances.shape, distances)

        # Filter ids by blacklist and distance
        filtered_ids = []
        for i, identifier in enumerate(results["ids"][0]):
            if identifier not in blacklist and distances[i] < 0.1:
                filtered_ids.append(identifier)

        # If there are fewer samples than target, generate a few more
        if len(filtered_ids) < self.max_samples:
            loss = distances.sum() / (samples / self.max_samples)
            self.queue.put(Task(loss, prompt, params))

        if not filtered_ids:
            raise HTTPException(status_code=404, detail="No valid phrase found")

        return random.choice(filtered_ids)

    def load(
        self, identifier: str, voices: list[str]
    ) -> (list[str], list[bytes], list[float], list[int]):
        phrases = self.get_phrases(identifier)
        voice_mapping = [i % 2 for i in range(len(phrases))]
        audios, durations = self.get_audios(identifier, voices, voice_mapping)
        return phrases, audios, durations, voice_mapping

    def get_phrases(self, identifier: str) -> list[str]:
        return load_json(f"{self.cache_dir}/{identifier}/phrases.json")

    def get_audios(
        self, identifier: str, voices: list[str], voice_mapping: list[int]
    ) -> (list[bytes], list[float]):
        audios = []
        durations = []
        for i, voice in enumerate(voice_mapping):
            path = f"{self.cache_dir}/{identifier}/{voices[voice]}/{i}.ogg"
            with open(path, "rb") as f:
                audios.append(f.read())
            with audioread.audio_open(path) as f:
                durations.append(f.duration)

        return audios, durations

    def validate(self):
        index = 0
        page_size = 100
        while True:
            results = self.collection.get(limit=page_size, offset=index)
            index += page_size
            if results["ids"]:
                for identifier in results["ids"]:
                    self.validate_identifier(identifier)
            else:
                break

    def validate_identifier(self, identifier: str):
        if os.path.exists(f"{self.cache_dir}/{identifier}/phrases.json"):
            # Check if all audios exist
            params = load_json(f"{self.cache_dir}/{identifier}/params.json")
            valid_voices = self.environment.get_valid_voices(params)
            count = self.populate_audios(
                identifier, self.get_phrases(identifier), valid_voices
            )
            if count > 0:
                logger.info(f"Generated {count} missing voices for {identifier}.")
        else:
            # Delete from database
            self.collection.delete(ids=[identifier])
            logger.warning(f"Deleted broken phrase {identifier}")


def init(configurator: Configurator):
    configurator.register("Phrasey", "Generates phrases for situations.")

    phraseys: dict[str, Phrasey] = {
        "minecraft": Phrasey("cache/phrasey/minecraft", MinecraftEnvironment()),
    }

    @configurator.get("/v1/phrasey/stats")
    def get_stats():
        return {
            environment: {
                "count": phrasey.collection.count(),
                "queue": phrasey.queue.qsize(),
            }
            for environment, phrasey in phraseys.items()
        }

    @configurator.get("/v1/phrasey/{environment}")
    def get_phrase(
        environment: str,
        params: str,
        voices: str,
        language: str = "en",
        blacklist: str = "",
    ):
        assert language == "en"

        if environment not in phraseys:
            return HTTPException(status_code=404, detail="Invalid environment")

        phrasey = phraseys[environment]

        # Prepare parameters
        params = json.loads(params)

        # Parse voices
        voices = [v.strip() for v in voices.split(",")]
        blacklist = {v.strip() for v in blacklist.split(",")}

        # Convert voice indices to voice names
        valid_voices = phrasey.environment.get_valid_voices(params)
        for i, voice in enumerate(voices):
            try:
                voices[i] = valid_voices[int(voice) % len(valid_voices)]
            except ValueError:
                pass

        # Validate voices
        for voice in voices:
            if voice not in valid_voices:
                return HTTPException(status_code=404, detail="Invalid voice")

        # Fetch an identifier
        try:
            identifier = phrasey.query(params, blacklist)
        except HTTPException as e:
            return e

        # Load phrases and audios
        phrases, audios, durations, voice_mapping = phraseys[environment].load(
            identifier, voices
        )

        return {
            "identifier": identifier,
            "phrases": phrases,
            "audios": [base64.b64encode(audio).decode("utf-8") for audio in audios],
            "durations": durations,
            "voice_mapping": voice_mapping,
        }


def main():
    phrasey = Phrasey("cache/phrasey", MinecraftEnvironment())

    params = {
        "task": "attack",
        "entity": "pillager",
        "biome": "desert",
        "weather": "thunderstorm",
        "time": "noon",
        "nearby": "pig",
        "weapon": "iron axe",
        "armor": "diamond helmet",
        "health": "high",
        "target": "player",
        "target_weapon": "diamond sword",
    }

    try:
        identifier = phrasey.query(params)
        phrasey.load(identifier, ["pirate"])
    except HTTPException as e:
        print(e)

    phrasey.thread.join()


if __name__ == "__main__":
    main()
