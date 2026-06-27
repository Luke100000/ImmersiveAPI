from typing import List

from fastapi import FastAPI, HTTPException
from horde_openai_proxy import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    Model,
    completions_to_openai_response,
    filter_models,
    get_horde_completion,
    openai_to_horde,
)
from jinja2 import TemplateError
from starlette.requests import Request

from app.configurator import Configurator

app = FastAPI()


def init(configurator: Configurator) -> List:
    configurator.register("Horde", "Horde related endpoints.")

    @configurator.get("/v1/chat/models")
    def get_chat_models(
        names: str = "",
        clean_names: str = "",
        base_models: str = "",
        templates: str = "",
        min_size: float = 0,
        max_size: float = -1,
        quant: str = "",
        backends: str = "",
    ) -> List[Model]:
        return filter_models(
            set(n.strip() for n in names.split(",") if n.strip()),
            set(n.strip() for n in clean_names.split(",") if n.strip()),
            set(n.strip() for n in base_models.split(",") if n.strip()),
            set(n.strip() for n in templates.split(",") if n.strip()),
            set(n.strip() for n in backends.split(",") if n.strip()),
            set(n.strip() for n in quant.split(",") if n.strip()),
            min_size=min_size,
            max_size=max_size,
        )

    def deduplicate(messages: list[dict]) -> list[dict]:
        """
        Deduplicate messages in the format of OpenAI chat completion API.
        :param messages: List of messages.
        :return: List of deduplicated messages.
        """
        last_role = None
        deduplicated = []
        for message in messages:
            if message["role"] == last_role:
                deduplicated[-1]["content"] += message["content"]
            else:
                deduplicated.append(message)
                last_role = message["role"]
        return deduplicated

    @configurator.post("/v1/chat/completions")
    def post_chat_completion(
        request: Request, body: ChatCompletionRequest
    ) -> ChatCompletionResponse:
        token = request.headers["authorization"].lstrip("Bearer ")

        try:
            try:
                horde_request = openai_to_horde(body)
            except TemplateError:
                # TODO: Meh
                body.messages[0]["role"] = "user"
                body.messages = deduplicate(body.messages)
                horde_request = openai_to_horde(body)

            completions = get_horde_completion(
                token, horde_request, slow_workers=False, allow_downgrade=True
            )
        except ValueError as e:
            raise HTTPException(status_code=406, detail=str(e))

        return completions_to_openai_response(completions)

    return [get_chat_models, post_chat_completion]
