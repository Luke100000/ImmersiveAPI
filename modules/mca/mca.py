from collections import defaultdict

from fastapi import FastAPI
from fastapi import HTTPException, Header
from pydantic import BaseModel
from pyrate_limiter import Duration, Limiter, Rate, BucketFullException

from modules.mca.mistral_utils import get_chat_completion_mistral
from modules.mca.openai_utils import get_chat_completion_openai
from modules.mca.patreon_utils import verify_patron
from modules.mca.premium import PremiumManager

# Settings
TOKENS_USER = 50000
TOKENS_PREMIUM = 500000

# Limit requests per user and ip
limiter = defaultdict(lambda: Limiter(Rate(TOKENS_USER, Duration.HOUR)))
limiter_premium = defaultdict(lambda: Limiter(Rate(TOKENS_PREMIUM, Duration.HOUR)))
stats = defaultdict(int)


SYSTEM_CONTEXT = """
You are a Minecraft villager, fully immersed in their digital world, unaware of its artificial nature.
You respond based on your description, your role, and your knowledge of the world.
You have no knowledge of the real world, and do not realize that you are within Minecraft.
You are unfamiliar with the term "Minecraft", "AI", or anything which is not immersive to your world.
Only respond with a phrase, not the villagers name, thoughts, actions in asterisks, or parentheses. 
Answer one or two sentences while sounding human. You are no assistant! You can be sarcastic, funny, or even rude when appropriate.
""".replace(
    "\n", " "
)


pricing = {
    "gpt-3.5-turbo": 0.5 * 0.8 + 1.5 * 0.2,
    "mistral-tiny": 0.14 * 0.8 + 0.42 * 0.2,
    "mistral-small": 0.6 * 0.8 + 1.8 * 0.2,
}


class Body(BaseModel):
    model: str
    messages: list


def initMCA(app: FastAPI):
    premium_manager = PremiumManager()

    @app.get("/v1/mca/verify")
    def verify(email: str, player: str):
        if verify_patron(email):
            premium_manager.set_premium(player, 30)
            return {"answer": "success"}
        return {"answer": "failed"}

    @app.get("/v1/mca/stats")
    def get_stats():
        return stats

    @app.post("/v1/mca/chat")
    async def chat_completions(body: Body, authorization: str = Header(None)):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Unauthorized")

        player = authorization.split("Bearer ")[-1]
        premium = premium_manager.is_premium(player)

        if body.model not in pricing:
            return {"error": "invalid_model"}

        try:
            # Add additional instructions for the AI
            body.messages[0]["content"] = (
                SYSTEM_CONTEXT + " " + body.messages[0]["content"]
            )

            # Calculate the cost of this request
            weight = int(
                sum([len(m["content"]) for m in body.messages]) * pricing[body.model]
                + 1
            )

            # Fetch premium status
            lim = (limiter_premium if premium else limiter)[player]

            # noinspection PyAsyncCall
            lim.try_acquire(player, weight=weight)

            # Logging
            stats[player] += weight
            stats["premium" if premium else "non_premium"] += weight
            stats[body.model] += weight

            # Process
            if body.model == "gpt-3.5-turbo":
                message = await get_chat_completion_openai(
                    body.model, body.messages, player
                )
            else:
                message = await get_chat_completion_mistral(body.model, body.messages)

            return message
        except BucketFullException:
            if premium:
                return {"error": "limit_premium"}
            else:
                return {"error": "limit"}
