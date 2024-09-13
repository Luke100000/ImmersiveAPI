import json
import os

from dotenv import load_dotenv

load_dotenv()

# TODO replace with langchain
from litellm import completion  # noqa: E402

system = """
You a phrase generator for a video game, producing a single immersive sentence a virtual entity would say after a given sequence of events and instructions.
Make use of the provided information.
Do not produce interjections, further explanations, quotation marks, or parentheses.
You stay immersive and in-character, you are not aware that you are in a game.
"""


def clean_text(text: str):
    text = text.split(":")[-1]
    text = text.replace('"', "")
    return text.strip()


def generate_phrases(
    prompt: str, dialogue: bool = False, model: str = "open-mistral-7b"
):
    history = [
        {
            "role": "system",
            "content": system
            + "\n"
            + (
                "Provide this dialogue between two entities as a JSON list. Try to aim for 2 to 5 phrases."
                if dialogue
                else "Provide 10 such phrases as a JSON list."
            ),
        },
        {"role": "user", "content": prompt},
    ]
    response = completion(
        model=model,
        custom_llm_provider="mistral",
        base_url="https://api.mistral.ai/v1",
        api_key=os.getenv("MISTRAL_API_KEY"),
        messages=history,
        response_format={"type": "json_object"},
        temperature=0.8,
        max_tokens=1024,
    )
    phrases = response.choices[0].message.content
    phrases = json.loads(phrases)
    phrases = [clean_text(t) for t in phrases]
    return phrases
