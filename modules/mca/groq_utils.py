import os
from functools import cache

from dotenv import load_dotenv
from groq import Groq

load_dotenv()


@cache
def get_client():
    return Groq(
        api_key=os.environ.get("GROQ_API_KEY"),
    )


MAPPING = {
    "mixtral-8x7b": "mixtral-8x7b-32768",
    "llama3-70b": "llama3-70b-8192",
    "llama3-8b": "llama3-8b-8192",
}


async def get_chat_completion_groq(model: str, messages: list):
    chat_completion = get_client().chat.completions.create(
        messages=messages,
        model=MAPPING[model],
    )
    return chat_completion
