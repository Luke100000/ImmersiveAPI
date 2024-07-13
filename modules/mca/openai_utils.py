from functools import cache

from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()


@cache
def get_client():
    return AsyncOpenAI()


async def check_prompt_openai(prompt: list):
    # Check if content is a TOS violation
    user_prompt = "\n".join([m["content"] for m in prompt if m["role"] == "user"])
    flags = (
        (await get_client().moderations.create(input=user_prompt)).results[0].categories
    )
    return flags.sexual or flags.self_harm or flags.violence_graphic
