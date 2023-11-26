import os
from typing import List

import openai
from dotenv import load_dotenv

load_dotenv()

openai.api_key = os.getenv("OPEN_AI")


def generate_phrase(events: List[str]):
    conversation_history = [
        {
            "role": "system",
            "content": "You are a phrase generator, producing a short immersive phrase a Minecraft entity would say after a given sequence of events. Make use of information in the events and from the Minecraft world. Output TTS-ready, do not produce interjections. Tend to produce short sentences.",
        },
        {"role": "user", "content": " ".join(events)},
    ]

    response = openai.chat.completions.create(
        model="gpt-4-1106-preview",
        messages=conversation_history,
        max_tokens=32,
        stop=["\n"],
    )

    completion = response.choices[0].message.content
    completion = completion.replace('"', "").strip()

    return completion
