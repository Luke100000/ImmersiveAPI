from typing import List

from fastapi import FastAPI, HTTPException
from horde_openai_proxy import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    Model,
    get_horde_completion,
    openai_to_horde,
    filter_models,
    completions_to_openai_response,
)
from starlette.requests import Request

from main import Configurator

app = FastAPI()


def init(configurator: Configurator) -> List:
    configurator.register("Horde", "Horde related endpoints.")

    @configurator.get("/v1/chat/models")
    def get_chat_models(
        names: str = "",
        clean_names: str = "",
        base_models: str = "",
        min_size: float = 0,
        max_size: float = -1,
        quant: str = "",
        backends: str = "",
    ) -> List[Model]:
        return filter_models(
            set(n.strip() for n in names.split(",") if n.strip()),
            set(n.strip() for n in clean_names.split(",") if n.strip()),
            set(n.strip() for n in base_models.split(",") if n.strip()),
            set(n.strip() for n in backends.split(",") if n.strip()),
            set(n.strip() for n in quant.split(",") if n.strip()),
            min_size=min_size,
            max_size=max_size,
        )

    @configurator.post("/v1/chat/completions")
    def post_chat_completion(
        request: Request, body: ChatCompletionRequest
    ) -> ChatCompletionResponse:
        token = request.headers["authorization"].lstrip("Bearer ")

        try:
            horde_request = openai_to_horde(body)
            completions = get_horde_completion(token, horde_request)
        except ValueError as e:
            raise HTTPException(status_code=406, detail=str(e))

        return completions_to_openai_response(completions)

    return [get_chat_models, post_chat_completion]
