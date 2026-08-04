import os
from typing import Any

from langchain_openai import ChatOpenAI

MEMORY_MODEL = "openai/gpt-5.6-luna"


def get_client_kwargs() -> dict[str, Any]:
    return {
        "base_url": os.environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1"),
        "api_key": os.environ.get("LLM_API_KEY"),
    }


def get_chat_model(**kwargs: Any) -> ChatOpenAI:
    return ChatOpenAI(**get_client_kwargs(), **kwargs)
