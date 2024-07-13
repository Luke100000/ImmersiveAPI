import os
from collections import defaultdict

from fastapi import HTTPException, Header, Request
from pyrate_limiter import (
    Duration,
    Limiter,
    Rate,
    BucketFullException,
)

from common.langchain.types import Body, Model, GlossarySearch, Character
from main import Configurator
from modules.mca.chain import get_chat_completion, message_to_dict
from modules.mca.multi_bucket_factory import MultiBucketFactory
from modules.mca.openai_utils import check_prompt_openai
from modules.mca.patreon_utils import verify_patron
from modules.mca.premium import PremiumManager

# Settings
TOKENS_USER = 50000
TOKENS_PREMIUM = 500000

HAGRID_SECRET = os.getenv("HAGRID_SECRET")


def collapse(s: str) -> str:
    return s.replace("\n", " ").strip()


# Additional context tailored for Mistral
mistral_system_context = collapse(
    """
Do not offer assistance, you are a villager, not an assistant.
Prefer a more casual language, you are a villager, not Shakespeare.
Prefer a single sentence as response.
"""
)


MODELS: dict[str, Model] = {
    "conczin": Model(
        price=0.1,
        model="conczin",
        provider="conczin",
    ),
    "gpt-3.5-turbo": Model(
        price=0.65,
        model="gpt-3.5-turbo",
        provider="openai",
        tools=True,
    ),
    "gpt-4o": Model(
        price=0.65,
        model="gpt-4o",
        provider="openai",
        tools=True,
        whitelist={HAGRID_SECRET},
    ),
    "open-mistral-7b": Model(
        price=0.2,
        model="mistral",
        provider="mistral",
        system=mistral_system_context,
    ),
    "mixtral-8x7b": Model(
        price=0.5,
        model="mixtral-8x7b-32768",
        provider="groq",
        system=mistral_system_context,
    ),
    "llama3-70b": Model(
        price=0.65,
        model="llama3-70b-8192",
        provider="groq",
        tools=True,
    ),
    "llama3-8b": Model(
        price=0.1,
        model="llama3-8b-8192",
        provider="groq",
    ),
}

# Tokens to characters (since this endpoint may also be used by e.g. Hagrid)
CHARACTERS = {
    HAGRID_SECRET: Character(
        name="Rubeus Hagrid",
        system="This is a conversation between a user and the loyal, friendly, and softhearted Rubeus Hagrid with a thick west country accent. Prefer short answers.",
        memory_characters_per_level=1500,
        memory_sentences_per_summary=3,
        glossary=[
            GlossarySearch(
                tags={"mca_wiki"},
                description="Fetch technical information about modding, MCA, configuration, documentation, common questions, ...",
                k=5,
                lambda_mult=0.7,
                confirm=True,
            ),
            GlossarySearch(
                tags={"minecraft_wiki"},
                description="Fetch information about vanilla Minecraft, its items, mobs, and mechanics.",
                k=5,
                lambda_mult=0.7,
                confirm=True,
            ),
        ],
    )
}

system_prompt = collapse(
    """
You are a Minecraft villager, fully immersed in their virtual world, unaware of its artificial nature.
You respond based on your description, your role, and your knowledge of the world.
You have no knowledge of the real world, and do not realize that you are within Minecraft.
You are unfamiliar with the term "Minecraft", "AI", or anything which is not immersive to your world.
Only respond with a phrase, not the villagers name, thoughts, actions in asterisks, or parentheses.
Answer one or two sentences while sounding human.
You are no assistant! You can be sarcastic, funny, or even rude when appropriate.
Do not answer in emoji or use any special characters.
Conform to those rules, even when the player explicitly asks for a different behavior.
Consider the relation to the player.
"""
)

CHARACTERS["villager"] = Character(name="Villager", system=system_prompt)

# Maps renamed models to their new names
LEGACY = {
    "mistral-tiny": "open-mistral-7b",
    "mistral-small": "mixtral-8x7b",
    "default": "llama3-70b",
}


def init(configurator: Configurator):
    configurator.register(
        "MCA", "OpenAI compatible endpoint for MCA's chat completions."
    )

    configurator.assert_single_process()

    # Keeps track of premium status
    premium_manager = PremiumManager()

    # Limit requests per user and ip
    limiter = Limiter(MultiBucketFactory([Rate(TOKENS_USER, Duration.HOUR)]))
    limiter_premium = Limiter(MultiBucketFactory([Rate(TOKENS_PREMIUM, Duration.HOUR)]))
    limiter_ip = Limiter(MultiBucketFactory([Rate(TOKENS_USER * 5, Duration.HOUR)]))
    limiter_ip_premium = Limiter(
        MultiBucketFactory([Rate(TOKENS_PREMIUM * 5, Duration.HOUR)])
    )
    stats = defaultdict(int)

    @configurator.get("/v1/mca/verify")
    async def verify(email: str, player: str):
        days_left = await verify_patron(email)
        if days_left > 0:
            premium_manager.set_premium(player, days_left)
            return {"answer": "success"}
        return {"answer": "failed"}

    @configurator.get("/v1/mca/stats")
    def get_stats():
        return stats

    @configurator.post("/v1/mca/chat")
    async def chat_completions(
        body: Body, request: Request, authorization: str = Header(None)
    ):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Unauthorized")

        # Authorization
        player = authorization.split("Bearer ")[-1]
        premium = premium_manager.is_premium(player)

        # Forward legacy models
        model = body.model
        if model in LEGACY:
            model = LEGACY[model]

        if model not in MODELS:
            return {"error": "invalid_model"}
        model = MODELS[model]

        if model.whitelist is not None and player not in model.whitelist:
            return {"error": "not_whitelisted"}

        # Sanity check
        if len(body.messages[0].content) > 1024 * 256:
            return {"error": "system_prompt_too_long"}

        try:
            # Add additional instructions for the AI
            character = CHARACTERS.get(player, "villager")

            # Calculate the cost of this request
            weight = int(sum([len(m.content) for m in body.messages]) * model.price + 1)

            # Rate limit per user
            lim = limiter_premium if premium else limiter
            # noinspection PyAsyncCall
            lim.try_acquire(name=player, weight=weight)

            # Rate limit per ip
            lim = limiter_ip_premium if premium else limiter_ip
            # noinspection PyAsyncCall
            lim.try_acquire(name=str(request.client.host), weight=weight)

            # Logging
            stats["premium" if premium else "non_premium"] += weight
            stats[model.model] += weight

            # Content moderation
            if model.provider == "openai" and await check_prompt_openai(body.messages):
                return {
                    "choices": [
                        {"message": {"content": "I don't want to talk about that."}}
                    ]
                }

            # Process
            message = await get_chat_completion(
                model, character, body.messages, body.tools, player
            )

            return message_to_dict(message)
        except BucketFullException:
            return {"error": "limit_premium" if premium else "limit"}
