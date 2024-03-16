import os
from datetime import datetime

import requests
from dotenv import load_dotenv
from patreon.utils import user_agent_string

load_dotenv()

access_token = os.getenv("PATREON_API_KEY")
campaign_id = os.getenv("PATREON_CAMPAIGN_ID")


def fetch_members(page_size: int = 100):
    members = []
    cursor = None
    while True:
        params = [
            f"fields[member]="
            + "%2C".join(
                [
                    "pledge_relationship_start",
                    "email",
                    "campaign_lifetime_support_cents",
                ]
            ),
            f"filter[campaign_id]={campaign_id}",
            f"sort=pledge_relationship_start",
            (f"page[cursor]=" + cursor) if cursor else "",
            f"page[count]={page_size}",
        ]

        response = requests.get(
            f"https://www.patreon.com/api/oauth2/v2/campaigns/{campaign_id}/members?"
            + "&".join(params),
            headers={
                "Authorization": "Bearer {}".format(access_token),
                "User-Agent": user_agent_string(),
            },
        )

        members += [r["attributes"] for r in response.json()["data"]]

        cursor = response.json()["meta"]["pagination"]["cursors"]["next"]
        if not cursor:
            break

    for m in members:
        if "pledge_relationship_start" in m:
            date1 = datetime.strptime(
                m["pledge_relationship_start"], "%Y-%m-%dT%H:%M:%S.%f%z"
            )
            date2 = datetime.now(date1.tzinfo)
            m["days_left"] = 35 - (date2 - date1).days

    return members


async def verify_patron(email: str) -> bool:
    email = email.lower().strip()

    email_to_user = {
        m["email"].lower().strip(): m
        for m in fetch_members()
        if m["campaign_lifetime_support_cents"] > 0
    }

    return email_to_user[email]["days_left"] if email in email_to_user else 0
