import hashlib
from functools import cache
from typing import List

from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()


@cache
def get_client():
    return AsyncOpenAI()


async def get_chat(model: str, messages: List, player: str):
    return await get_client().chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.9,
        max_tokens=150,
        stop=[f"{player}:"],
        user=hashlib.sha256(player.encode("UTF-8")).hexdigest(),
    )


async def get_chat_completion_openai(model: str, prompt: list, player: str):
    # Check if content is a TOS violation
    user_prompt = "\n".join([m["content"] for m in prompt if m["role"] == "user"])
    flags = (
        (await get_client().moderations.create(input=user_prompt)).results[0].categories
    )

    if flags.sexual or flags.self_harm or flags.violence_graphic:
        return {
            "choices": [{"message": {"content": "I don't want to talk about that."}}]
        }

    content = await get_chat(model, prompt, player)

    if not content:
        return {"choices": [{"message": {"content": "..."}}]}

    return content
