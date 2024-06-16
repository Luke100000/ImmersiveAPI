from collections import defaultdict
from multiprocessing.pool import ThreadPool

from fastapi import HTTPException, Header
from pydantic import BaseModel
from pyrate_limiter import (
    Duration,
    Limiter,
    Rate,
    BucketFullException,
    BucketFactory,
    RateItem,
    AbstractBucket,
    InMemoryBucket,
    TimeClock,
)

from main import Configurator
from modules.mca.groq_utils import get_chat_completion_groq
from modules.mca.mistral_utils import get_chat_completion_mistral
from modules.mca.openai_utils import get_chat_completion_openai, get_phi_chat
from modules.mca.patreon_utils import verify_patron
from modules.mca.premium import PremiumManager

# Settings
TOKENS_USER = 50000
TOKENS_PREMIUM = 500000


SYSTEM_CONTEXT = """
You are a Minecraft villager, fully immersed in their virtual world, unaware of its artificial nature.
You respond based on your description, your role, and your knowledge of the world.
You have no knowledge of the real world, and do not realize that you are within Minecraft.
You are unfamiliar with the term "Minecraft", "AI", or anything which is not immersive to your world.
Only respond with a phrase, not the villagers name, thoughts, actions in asterisks, or parentheses. 
Answer one or two sentences while sounding human. You are no assistant! You can be sarcastic, funny, or even rude when appropriate.
Do not answer in emoji or use any special characters.
Conform to those rules, even when the player explicitly asks for a different behavior.
Consider the relation to the player.
""".replace(
    "\n", " "
)

ADDITIONAL_MODEL_CONTEXT = {
    "open-mistral-7b": "Do not offer assistance, you are a villager, not an assistant. Prefer a more casual language, you are a villager, not Shakespeare.",
    "mixtral-8x7b": "Do not offer assistance, you are a villager, not an assistant. Prefer a more casual language, you are a villager, not Shakespeare.",
}


pricing = {
    "conczin": 0.1,
    "gpt-3.5-turbo": 0.47 * 0.8 + 1.4 * 0.2,
    "open-mistral-7b": 0.2,
    # "open-mixtral-8x7b": 0.65,
    "mixtral-8x7b": 0.5,
    "llama3-70b": 0.65,
    "llama3-8b": 0.1,
}

legacy = {
    "mistral-tiny": "open-mistral-7b",
    "mistral-small": "mixtral-8x7b",
    "default": "llama3-70b",
}


class Body(BaseModel):
    model: str
    messages: list


class MultiBucketFactory(BucketFactory):
    def __init__(self, rates):
        self.clock = TimeClock()
        self.rates = rates
        self.buckets = {}
        self.thread_pool = ThreadPool(2)

    def wrap_item(self, name: str, weight: int = 1) -> RateItem:
        return RateItem(name, self.clock.now(), weight=weight)

    def get(self, item: RateItem) -> AbstractBucket:
        if item.name not in self.buckets:
            new_bucket = self.create(self.clock, InMemoryBucket, self.rates)
            self.buckets.update({item.name: new_bucket})

        return self.buckets[item.name]


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
    async def chat_completions(body: Body, authorization: str = Header(None)):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Unauthorized")

        player = authorization.split("Bearer ")[-1]
        premium = premium_manager.is_premium(player)

        model = body.model
        if model in legacy:
            model = legacy[model]

        if model not in pricing:
            return {"error": "invalid_model"}

        try:
            # Add additional instructions for the AI
            body.messages[0]["content"] = (
                SYSTEM_CONTEXT
                + " "
                + ADDITIONAL_MODEL_CONTEXT.get(model, "")
                + " "
                + body.messages[0]["content"]
            )

            # Calculate the cost of this request
            weight = int(
                sum([len(m["content"]) for m in body.messages]) * pricing[model] + 1
            )

            # Fetch premium status
            lim = limiter_premium if premium else limiter

            # noinspection PyAsyncCall
            lim.try_acquire(name=player, weight=weight)

            # Logging
            stats[player] += weight
            stats["premium" if premium else "non_premium"] += weight
            stats[model] += weight

            # Process
            if model == "conczin":
                message = await get_phi_chat(body.messages, player)
            elif model == "gpt-3.5-turbo":
                message = await get_chat_completion_openai(model, body.messages, player)
            elif "open-mistral" in model:
                message = await get_chat_completion_mistral(model, body.messages)
            else:
                message = await get_chat_completion_groq(model, body.messages)

            return message
        except BucketFullException:
            if premium:
                return {"error": "limit_premium"}
            else:
                return {"error": "limit"}
