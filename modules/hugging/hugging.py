import asyncio
import hashlib
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from typing import List, Any, Optional, Union

from fastapi import FastAPI, UploadFile
from pydantic import BaseModel
from starlette.responses import Response, StreamingResponse

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


worker = ThreadPoolExecutor(max_workers=1)


def expand_args(func, future, args, kwargs):
    future.set_result(func(*args, **kwargs))


def run(func, *args, **kwargs):
    future = asyncio.get_running_loop().create_future()
    worker.submit(expand_args, func, future, args, kwargs)
    return future


def initHugging(app: FastAPI):
    @app.post("/v1/text/mistral")
    async def post_text_mistral(params: TextRequest):
        text = await run(
            generate_text,
            params.messages,
            **params.model_dump(exclude={"messages"}),
        )
        return StreamingResponse(text) if params.stream else Response(text)

    # @app.post("/v1/image/sdxl-turbo")
    # async def post_image_sdxl_turbo(params: ImageRequest):
    #    image = await run(generate_image, **params.model_dump())
    #    buffer = io.BytesIO()
    #    image.save(buffer, format="PNG")
    #    return Response(content=buffer.getvalue(), media_type="image/png")

    @app.get("/v1/tts/xtts-v2/queue")
    async def get_tts_xtts_model():
        return worker._work_queue.qsize()

    @app.get("/v1/tts/xtts-v2/model")
    async def get_tts_xtts_model():
        return await run(
            lambda: {
                "speakers": get_speakers(),
                "languages": get_languages(),
                "base_speakers": get_base_speakers(),
            }
        )

    @app.post("/v1/tts/xtts-v2")
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
            cache_key = f"cache/tts/{language}-{speaker}/{text_hash}.{file_format}"
            os.makedirs(os.path.dirname(cache_key), exist_ok=True)

            # If a cached file is found, return it
            if os.path.exists(cache_key):
                with open(cache_key, "rb") as f:
                    return Response(content=f.read(), media_type=f"audio/{file_format}")

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
        c = run(
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
