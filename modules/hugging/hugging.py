import asyncio
import hashlib
import os
import tempfile
from typing import List, Any, Optional, Union

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
from modules.hugging.mistral import generate_text


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

    # While thread safe itself, this module makes use of an executor anyway
    configurator.set_non_thread_safe()

    @configurator.post("/v1/text/mistral")
    async def post_text_mistral(params: TextRequest):
        text = await get_primary_executor().submit(
            0,
            generate_text,
            params.messages,
            **params.model_dump(exclude={"messages"}),
        )
        return StreamingResponse(text) if params.stream else Response(text)

    @configurator.get("/v1/tts/xtts-v2/queue")
    async def get_tts_xtts_model():
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

            # Also scan for english, if the phrase is identical in most cases its fine to use the English version
            for scan_language in ["en", language]:
                cache_key = (
                    f"cache/tts/{scan_language}-{speaker}/{text_hash}.{file_format}"
                )
                os.makedirs(os.path.dirname(cache_key), exist_ok=True)

                # If a cached file is found, return it
                if os.path.exists(cache_key):
                    with open(cache_key, "rb") as f:
                        return Response(
                            content=f.read(), media_type=f"audio/{file_format}"
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
