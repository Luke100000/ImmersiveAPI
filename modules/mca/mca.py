import os

import groq
from fastapi import HTTPException, Header, Request
from groq import BaseModel
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
    "gpt-3.5-turbo": Model(
        price=0.65,
        model="gpt-3.5-turbo",
        provider="openai",
        tools=True,
    ),
    "gpt-4o-mini": Model(
        price=0.3,
        model="gpt-4o-mini",
        provider="openai",
        tools=True,
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
    "llama3.1-70b": Model(
        price=0.65,
        model="llama-3.1-70b-versatile",
        provider="groq",
        tools=True,
    ),
    "llama3-8b": Model(
        price=0.1,
        model="llama3-8b-8192",
        provider="groq",
    ),
    "llama3.1-8b": Model(
        price=0.1,
        model="llama-3.1-8b-instant",
        provider="groq",
    ),
    "gemma2-9b": Model(
        price=0.2,
        model="gemma2-9b-it",
        provider="groq",
    ),
    "horde": Model(
        price=0.1,
        model="horde",
        provider="horde",
    ),
}

# Tokens to characters (since this endpoint may also be used by e.g. Hagrid)
CHARACTERS = {
    HAGRID_SECRET: Character(
        name="Rubeus Hagrid",
        system="This is a conversation between users and the loyal, friendly, and softhearted Rubeus Hagrid with a thick west country accent. Generate a short discord-message-respond in his thick west country accent!",
        memory_characters_per_level=1200,
        memory_sentences_per_summary=3,
        memory_model="llama-3.1-70b-versatile",
        langsmith_project="hagrid",
        stop=[],
        glossary={
            "mca_wiki_fast": GlossarySearch(
                tags={"mca_wiki"},
                description="Fetch technical information about modding, MCA, configuration, documentation, common questions, ...",
                k=3,
                lambda_mult=0.8,
                always=False,
            ),
            "mca_wiki": GlossarySearch(
                tags={"mca_wiki"},
                description="Fetch technical information about modding, MCA, configuration, documentation, common questions, ...",
                k=7,
                lambda_mult=0.7,
                always=False,
            ),
            "minecraft_wiki": GlossarySearch(
                tags={"minecraft_wiki"},
                description="Fetch information about vanilla Minecraft, its items, mobs, and mechanics.",
                k=5,
                lambda_mult=0.7,
                always=False,
            ),
        },
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
    "default": "gpt-4o-mini",
}


class ModelStats(BaseModel):
    count: int = 0
    cost: int = 0
    premium_count: int = 0
    premium_cost: int = 0
    rate_limited: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    kudos: int = 0


class Stats(BaseModel):
    summary: ModelStats = ModelStats()
    models: dict[str, ModelStats] = dict()
    actual_models: dict[str, ModelStats] = dict()

    def refresh(self):
        self.summary = ModelStats()
        for model in self.models.values():
            self.summary.count += model.count
            self.summary.cost += model.cost
            self.summary.premium_count += model.premium_count
            self.summary.premium_cost += model.premium_cost
            self.summary.rate_limited += model.rate_limited
            self.summary.prompt_tokens += model.prompt_tokens
            self.summary.completion_tokens += model.completion_tokens
            self.summary.cached_tokens += model.cached_tokens
            self.summary.kudos += model.kudos


def safe_get(d: dict, k: str) -> int:
    v = 0 if d is None else d.get(k, 0)
    return 0 if v is None else v


def init(configurator: Configurator):
    """
    The system prompt encodes additional flags for session management and glossary usage.
    `[key:value][key:value]...Rest of the system prompt`
    * `world_id`: The world id for the session, e.g. the guild id or world UUID.
    * `player_id`: The player id
    * `character_id`: The character id, e.g. the villager UUID.
    * `use_memory`: Whether to use memory for this session, otherwise use classic in-context memory.
    * `shared_memory`: Whether to share memory across the world, otherwise separate memory per player.
    """

    configurator.register(
        "MCA", "OpenAI compatible endpoint for MCA's chat completions."
    )

    # Keeps track of premium status
    premium_manager = PremiumManager()

    # Limit requests per user and ip
    limiter = Limiter(MultiBucketFactory([Rate(TOKENS_USER, Duration.HOUR)]))
    limiter_premium = Limiter(MultiBucketFactory([Rate(TOKENS_PREMIUM, Duration.HOUR)]))
    limiter_ip = Limiter(MultiBucketFactory([Rate(TOKENS_USER * 5, Duration.HOUR)]))
    limiter_ip_premium = Limiter(
        MultiBucketFactory([Rate(TOKENS_PREMIUM * 5, Duration.HOUR)])
    )

    stats = Stats()

    @configurator.get("/v1/mca/verify")
    def verify(email: str, player: str):
        days_left = verify_patron(email)
        if days_left > 0:
            premium_manager.set_premium(player, days_left)
            return {"answer": "success"}
        return {"answer": "failed"}

    @configurator.get("/v1/mca/stats")
    def get_stats() -> Stats:
        stats.refresh()
        return stats

    @configurator.post("/v1/mca/chat")
    def chat_completions(
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
            character = CHARACTERS.get(player, CHARACTERS["villager"])

            # Calculate the cost of this request
            weight = int(sum([len(m.content) for m in body.messages]) * model.price + 1)

            # Rate limit per user
            lim = limiter_premium if premium else limiter
            # noinspection PyAsyncCall
            lim.try_acquire(name=player, weight=weight)

            # Rate limit per ip
            lim = limiter_ip_premium if premium else limiter_ip
            # noinspection PyAsyncCall
            lim.try_acquire(
                name=str(request.client.host),  # pyright: ignore [reportOptionalMemberAccess]
                weight=weight,
            )  # pyright: ignore [reportOptionalMemberAccess]

            # Content moderation
            if model.provider == "openai" and check_prompt_openai(body.messages):
                return {
                    "choices": [
                        {"message": {"content": "I don't want to talk about that."}}
                    ]
                }

            # Process
            rate_limited = False
            try:
                message = get_chat_completion(
                    model,
                    character,
                    body.messages,
                    body.tools,
                    player,
                    langsmith_project=character.langsmith_project,
                )
            except groq.RateLimitError:
                # TODO: Remove once Groq limits are removed
                rate_limited = True
                message = get_chat_completion(
                    MODELS[LEGACY["default"]],
                    character,
                    body.messages,
                    body.tools,
                    player,
                )

            # Logging
            if rate_limited:
                stats.models[model.model].rate_limited += 1

            actual_model_name = message.response_metadata.get("model_name", model.model)
            for model_name, stats_container in [(model.model, stats.models)] + [
                (actual_model_name, stats.actual_models)
            ]:
                if model_name not in stats_container:
                    stats_container[model_name] = ModelStats()
                model_stats = stats_container[model_name]

                token_usage = message.response_metadata.get("token_usage", {})
                model_stats.count += 1
                model_stats.cost += weight
                if premium:
                    model_stats.premium_count += 1
                    model_stats.premium_cost += weight
                model_stats.kudos += safe_get(token_usage, "kudos")
                model_stats.prompt_tokens += safe_get(token_usage, "prompt_tokens")
                model_stats.completion_tokens += safe_get(
                    token_usage, "completion_tokens"
                )
                model_stats.cached_tokens += safe_get(
                    token_usage.get("prompt_tokens_details", {}), "cached_tokens"
                )

            # Convert to a partial OpenAI response
            return message_to_dict(message)
        except BucketFullException:
            return {"error": "limit_premium" if premium else "limit"}

    assert [init, verify, get_stats, chat_completions]
