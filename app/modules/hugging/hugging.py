import hashlib
import os
import subprocess
import threading
from enum import Enum
from typing import Any, Iterable, List, Optional

from pydantic import BaseModel
from starlette.responses import Response, StreamingResponse

from app.configurator import Configurator

from .coqui import (
    generate_speech,
    get_base_speakers,
    get_languages,
    get_speakers,
)
from .piper_utils import (
    blacklist,
    get_best_voices,
    get_gender_lookup,
    speak,
)


class Message(BaseModel):
    role: str
    content: str

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


class TextRequest(BaseModel):
    messages: List[Message]

    temperature: float = 0.2
    top_p: float = 0.95
    top_k: int = 40
    stop: Optional[List[str]] = None
    seed: Optional[int] = None
    max_tokens: int = 100
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0
    repeat_penalty: float = 1.1
    stream: bool = False


class ImageRequest(BaseModel):
    prompt: str
    num_inference_steps: int = 2


def init(configurator: Configurator):
    configurator.register(
        "Hugging", "Endpoints mostly relying on HuggingFace or similar ML models."
    )

    @configurator.get("/v1/tts/xtts-v2/model", deprecated=True)
    def get_tts_xtts_model():
        return {
            "speakers": get_speakers(),
            "languages": get_languages(),
            "base_speakers": get_base_speakers(),
        }

    @configurator.post("/v1/tts/xtts-v2", deprecated=True)
    def post_tts_xtts(
        text: str,
        language: str = "en",
        speaker: str = "male_1",
        file_format: str = "wav",
        cache: bool = False,
        prepare_speakers: int = 0,
        load_async: bool = False,
    ):
        # Deprecated parameters
        assert prepare_speakers is not None
        assert load_async is not None

        # Map generic speakers to actual speakers
        if get_base_speakers():
            speaker = get_base_speakers()[speaker]

        cache_key = None
        if cache:
            text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

            # Also scan for English if the phrase is identical, in most cases it's fine to use the English version
            for scan_language in ["en", language]:
                cache_key = (
                    f"cache/tts/{scan_language}-{speaker}/{text_hash}.{file_format}"
                )

                # If a cached file is found, return it
                if os.path.exists(cache_key):
                    with open(cache_key, "rb") as f:
                        return Response(
                            content=f.read(), media_type=f"audio/{file_format}"
                        )

        # Generate audio
        audio = generate_speech(
            text=text,
            speaker=speaker,
            language=language,
            file_format=file_format,
            file_path=cache_key,
        )

        return Response(content=audio, media_type=f"audio/{file_format}")

    @configurator.get("/v1/tts/piper/voices")
    async def get_tts_piper_voices(high_quality: bool = True):
        speakers = get_best_voices()

        if high_quality:
            speakers = {
                name: s for name, s in speakers.items() if s["name"] not in blacklist
            }

        genders = get_gender_lookup()

        languages = {}
        voices = []

        for speaker_name, s in speakers.items():
            code = s["language"]["code"]
            if code not in languages:
                languages[code] = {
                    "male": 0,
                    "female": 0,
                    "unknown": 0,
                }

            for speaker_id in range(s["num_speakers"]):
                if s["speaker_id_map"]:
                    vid = f"{speaker_name}:{speaker_id}"
                else:
                    vid = f"{speaker_name}:-1"

                gender = genders.get(vid, "unknown")
                languages[code][gender] += 1

                voices.append(
                    {
                        "id": vid,
                        "name": s["name"],
                        "language": s["language"]["code"],
                        "gender": gender,
                    }
                )

        return {
            "languages": languages,
            "voices": voices,
        }

    class PiperFormats(Enum):
        PCM = "pcm"
        WAV = "wav"
        OGG = "ogg"
        MP3 = "mp3"

    class PiperTTSRequestBody(BaseModel):
        text: str
        voice: str = "alan:-1"
        format: PiperFormats = PiperFormats.PCM

    def get_media_type(fmt: PiperFormats) -> str:
        if fmt == PiperFormats.PCM:
            return "audio/L16; rate=22050; channels=1"
        elif fmt == PiperFormats.WAV:
            return "audio/wav"
        elif fmt == PiperFormats.OGG:
            return "audio/ogg"
        elif fmt == PiperFormats.MP3:
            return "audio/mpeg"
        return "application/octet-stream"

    def convert_stream(pcm_iter: Iterable[bytes], fmt: PiperFormats) -> Iterable[bytes]:
        if fmt == PiperFormats.PCM:
            return pcm_iter

        proc = subprocess.Popen(
            [
                "ffmpeg",
                "-f",
                "s16le",
                "-ar",
                "22050",
                "-ac",
                "1",
                "-i",
                "pipe:0",
                "-f",
                fmt.value,
                "pipe:1",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

        def generate():
            def writer():
                for chunk in pcm_iter:
                    proc.stdin.write(chunk)
                proc.stdin.close()

            threading.Thread(target=writer, daemon=True).start()

            while True:
                out = proc.stdout.read(4096)
                if not out:
                    break
                yield out

        return generate()

    @configurator.post("/v1/tts/piper/speak")
    def get_tts_piper(body: PiperTTSRequestBody):
        pcm_iter = speak(body.text, body.voice)
        return StreamingResponse(
            convert_stream(pcm_iter, body.format),
            media_type=get_media_type(body.format),
        )
