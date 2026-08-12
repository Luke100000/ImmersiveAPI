import hashlib

from cachetools import TTLCache, cached

from app.configurator import Configurator
from app.crowdin_utils import get_cached_translator_names
from app.patreon_utils import fetch_members, get_member_list


def hash_email(email: str) -> str:
    return hashlib.sha256(email.encode("utf-8")).hexdigest()


def init(configurator: Configurator):
    configurator.register("Patreon", "Proxy for the Patreon API to list patrons.")

    @configurator.get("/v1/patron_names")
    @cached(TTLCache(maxsize=1, ttl=1800))
    def get_patron_names():
        return get_member_list()

    @configurator.get("/v1/translator_names")
    async def get_translator_names():
        return await get_cached_translator_names()

    @configurator.get("/v1/patron_tiers/{emails}")
    def get_patron_tiers(emails: str):
        verified = {}
        for m in fetch_members():
            if m["email"] and m["tiers"]:
                verified[hash_email(m["email"])] = m["tiers"]
        return {email: list(verified.get(email, [])) for email in emails.split(",")}

    @configurator.get("/v1/patrons")
    @cached(TTLCache(maxsize=1, ttl=1800))
    def get_patrons():
        members = sorted(
            (
                member
                for member in fetch_members()
                if member["campaign_lifetime_support_cents"] > 0
            ),
            key=lambda member: member["campaign_lifetime_support_cents"],
            reverse=True,
        )
        return [
            {
                "id": member["id"],
                "name": member["full_name"],
                "thumbnail": member["thumb_url"],
            }
            for member in members
        ]
