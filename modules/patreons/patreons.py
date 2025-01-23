import hashlib
import os
from collections import defaultdict

import patreon as patreon
from cachetools import cached, TTLCache

from main import Configurator
from modules.mca.patreon_utils import get_member_list, fetch_members

creator_access_token = os.getenv("PATREON_API_KEY")

api_client = patreon.API(creator_access_token)


def hash_email(email: str) -> str:
    return hashlib.sha256(email.encode("utf-8")).hexdigest()


def init(configurator: Configurator):
    configurator.register("Patreon", "Proxy for the Patreon API to list patrons.")

    @configurator.get("/v1/patron_names")
    @cached(TTLCache(maxsize=1, ttl=1800))
    def get_patron_names():
        return get_member_list()

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
        users = {}
        pledges = defaultdict(int)

        response = api_client.fetch_campaign(
            includes=["pledges"],
            fields={
                "reward": [],
                "campaign": [],
                "pledge": ["total_historical_amount_cents"],
                "user": ["full_name", "thumb_url"],
            },
        ).json_data["included"]

        for data in response:
            if data["type"] == "pledge":
                userid = data["relationships"]["patron"]["data"]["id"]
                pledges[userid] += data["attributes"]["total_historical_amount_cents"]
            elif data["type"] == "user":
                userid = data["id"]
                users[userid] = {
                    "name": data["attributes"]["full_name"],
                    "thumbnail": data["attributes"]["thumb_url"],
                }

        return sorted(
            [
                user | {"id": userid}
                for userid, user in users.items()
                if pledges[userid] > 0
            ],
            key=lambda user: pledges[user["id"]],
            reverse=True,
        )
