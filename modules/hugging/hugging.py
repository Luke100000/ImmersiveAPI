import asyncio
import tempfile
from concurrent.futures import ThreadPoolExecutor
from typing import List, Any, Optional, Union

from fastapi import FastAPI, UploadFile
from pydantic import BaseModel
from starlette.responses import Response, StreamingResponse

from modules.hugging.coqui import generate_speech
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


def expand_args(func, args, kwargs):
    return func(*args, **kwargs)


async def run(func, *args, **kwargs):
    return await asyncio.get_event_loop().run_in_executor(
        worker,
        expand_args,
        func,
        args,
        kwargs,
    )


# todo all initializers are not snake case
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

    @app.post("/v1/tts/xtts-v2")
    async def post_tts_xtts(
        text: str, speaker: Optional[str] = None, file: Union[UploadFile, None] = None
    ):
        if file is not None:
            f = tempfile.NamedTemporaryFile()
            f.write(await file.read())
            f.flush()
            speaker = f.name

        wav = await run(generate_speech, text=text, speaker=speaker)

        return Response(content=wav, media_type="audio/wav")
