from functools import cache

from dotenv import load_dotenv
from openai import OpenAI

from ...llm.types import Message, Role

load_dotenv()


@cache
def get_client():
    return OpenAI()


def check_prompt_openai(prompt: list[Message]):
    # Check if content is a TOS violation
    user_prompt = "\n".join([m.content for m in prompt if m.role == Role.user])
    flags = (get_client().moderations.create(input=user_prompt)).results[0].categories
    return flags.sexual or flags.self_harm or flags.violence_graphic
