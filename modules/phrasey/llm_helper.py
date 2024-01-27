import os
from typing import List

import openai
from dotenv import load_dotenv
from mistralai.client import MistralClient
from mistralai.models.chat_completion import ChatMessage

from modules.hugging.hugging import worker
from modules.hugging.mistral import generate_text

load_dotenv()

mistral_model = "mistral-tiny"

client = MistralClient(api_key=os.getenv("MISTRAL_API_KEY"))

openai.api_key = os.getenv("OPEN_AI")

context = "You are a phrase generator for a video game, producing a single immersive sentence a Minecraft entity would say after a given sequence of events. Make use of information in the events and from the Minecraft world. Do not produce interjections, further explanations, quotation marks, or parentheses."


def to_history(events: List[str]):
    return [
        {
            "role": "system",
            "content": context,
        },
        {"role": "user", "content": " ".join(events)},
    ]


def generate_phrase_openai(events: List[str]):
    response = openai.chat.completions.create(
        model="gpt-4-1106-preview",
        messages=to_history(events),
        max_tokens=32,
        stop=["\n"],
    )

    completion = response.choices[0].message.content
    completion = completion.replace('"', "").strip()

    return completion


def generate_phrase_mistral(events: List[str]):
    messages = [
        ChatMessage(role="system", content=context),
    ] + [ChatMessage(role="user", content=e) for e in events]

    # No streaming
    chat_response = client.chat(
        model=mistral_model,
        messages=messages,
    )

    return chat_response.choices[0].message.content


def generate_phrase(events: List[str], llm="local_mistral"):
    if llm == "local_mistral":
        # We use the worker here as well to prevent access from another thread
        phrase = worker.submit(
            generate_text, to_history(events), stop=["\n", "("]
        ).result()
    elif llm == "mistral":
        phrase = generate_phrase_mistral(events)
    elif llm == "openai":
        phrase = generate_phrase_openai(events)
    else:
        raise ValueError("Invalid LLM")

    phrase = phrase.split(":")[-1]

    return phrase.replace('"', "").strip()
