import asyncio
import hashlib
import tempfile
from typing import List, Any, Optional, Union

import aiofiles
import aiofiles.os
from fastapi import UploadFile
from pydantic import BaseModel
from starlette.responses import Response, StreamingResponse

from common.worker import get_primary_executor
from main import Configurator
from modules.hugging.coqui import (
    generate_speech,
    get_languages,
    get_speakers,
    get_base_speakers,
)
from modules.hugging.piper_utils import (
    get_best_voices,
    speak,
    get_gender_lookup,
    blacklist,
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

    @configurator.get("/v1/tts/xtts-v2/queue")
    def get_tts_xtts_queue():
        return get_primary_executor().queue.qsize()

    @configurator.get("/v1/tts/xtts-v2/model")
    async def get_tts_xtts_model():
        return await get_primary_executor().submit(
            0,
            lambda: {
                "speakers": get_speakers(),
                "languages": get_languages(),
                "base_speakers": get_base_speakers(),
            },
        )

    @configurator.post("/v1/tts/xtts-v2")
    async def post_tts_xtts(
        text: str,
        language: str = "en",
        speaker: Optional[str] = None,
        file_format: str = "wav",
        cache: bool = False,
        prepare_speakers: int = 0,
        load_async: bool = False,
        file: Union[UploadFile, None] = None,
    ):
        # Map generic speakers to actual speakers
        if speaker is not None and speaker in get_base_speakers():
            speaker = get_base_speakers()[speaker]

        cache_key = None
        if cache:
            text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

            # Also scan for english if the phrase is identical, in most cases its fine to use the English version
            for scan_language in ["en", language]:
                cache_key = (
                    f"cache/tts/{scan_language}-{speaker}/{text_hash}.{file_format}"
                )
                await aiofiles.os.makedirs("tmp", exist_ok=True)

                # If a cached file is found, return it
                if await aiofiles.os.path.exists(cache_key):
                    async with aiofiles.open(cache_key, "rb") as f:
                        return Response(
                            content=await f.read(), media_type=f"audio/{file_format}"
                        )

            # If an uncached file is found, load all other speakers as well
            if prepare_speakers > 0:
                for gender in ["male", "female"]:
                    for count in range(min(25, prepare_speakers)):
                        await asyncio.create_task(
                            post_tts_xtts(
                                text=text,
                                language=language,
                                speaker=f"{gender}_{count}",
                                file_format=file_format,
                                cache=True,
                                prepare_speakers=False,
                                load_async=True,
                            )
                        )

        # Save speaker audio to file
        speaker_wav = None
        if file is not None:
            f = tempfile.NamedTemporaryFile()
            f.write(await file.read())
            f.flush()
            speaker_wav = f.name

        # Generate audio
        c = get_primary_executor().submit(
            2 if load_async else 0,
            generate_speech,
            text=text,
            language=language,
            speaker=speaker,
            speaker_wav=speaker_wav,
            file_format=file_format,
            file_path=cache_key,
            overwrite=False,
        )

        # Don't wait for the audio to load if it's async
        if load_async:
            return Response(content="")

        audio = await c
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

    class PiperTTSRequestBody(BaseModel):
        text: str
        voice: str

    @configurator.post("/v1/tts/piper/speak")
    async def get_tts_piper(body: PiperTTSRequestBody):
        return StreamingResponse(
            speak(body.text, body.voice), media_type="audio/L16; rate=16000; channels=1"
        )
