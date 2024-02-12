import os

import aiohttp
from dotenv import load_dotenv
from mistralai.client import MistralClient

load_dotenv()

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
client = MistralClient(api_key=MISTRAL_API_KEY)


url = "https://api.mistral.ai/v1/chat/completions"

headers = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Authorization": f"Bearer {MISTRAL_API_KEY}",
}


async def get_chat_completion_mistral(model: str, messages: list):
    data = {
        "model": model,
        "messages": messages,
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as response:
            return await response.json()
