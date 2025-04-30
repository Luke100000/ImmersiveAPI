import os
from datetime import datetime

import requests
from cachetools import cached, TTLCache
from dotenv import load_dotenv
from patreon.utils import user_agent_string

load_dotenv()

access_token = os.getenv("PATREON_API_KEY")
campaign_id = os.getenv("PATREON_CAMPAIGN_ID")


@cached(TTLCache(maxsize=8, ttl=60))
def fetch_members(page_size: int = 1000) -> list[dict]:
    members = []
    cursor = None
    while True:
        params = [
            "include=currently_entitled_tiers%2Cuser",
            "fields[member]="
            + "%2C".join(
                [
                    "last_charge_date",
                    "patron_status",
                    "full_name",
                    "email",
                    "campaign_lifetime_support_cents",
                ]
            ),
            "fields[user]=" + "%2C".join(["hide_pledges"]),
            "sort=last_charge_date",
            ("page[cursor]=" + cursor) if cursor else "",
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

        response_json = response.json()

        users = {u["id"]: u for u in response_json["included"] if u["type"] == "user"}

        members += [
            {
                **r["attributes"],
                **users[r["relationships"]["user"]["data"]["id"]]["attributes"],
                "tiers": {
                    t["id"]
                    for t in r["relationships"]["currently_entitled_tiers"]["data"]
                },
            }
            for r in response_json["data"]
        ]

        cursor = response_json["meta"]["pagination"]["cursors"]["next"]
        if not cursor:
            break

    for m in members:
        if (
            "last_charge_date" in m
            and m["last_charge_date"]
            and m["patron_status"] == "active_patron"
        ):
            date1 = datetime.strptime(m["last_charge_date"], "%Y-%m-%dT%H:%M:%S.%f%z")
            date2 = datetime.now(date1.tzinfo)
            m["days_left"] = max(0, 35 - (date2 - date1).days)
        else:
            m["days_left"] = 0

    return members


def get_member_list():
    members = [m for m in fetch_members() if m["campaign_lifetime_support_cents"] > 0]
    sorted_members = sorted(
        members, key=lambda m: m["campaign_lifetime_support_cents"], reverse=True
    )
    return [m["full_name"] for m in sorted_members]


def verify_patron(email: str) -> bool:
    email = email.lower().strip()

    email_to_user = {
        m["email"].lower().strip(): m for m in fetch_members() if m["email"] is not None
    }

    return email_to_user[email]["days_left"] if email in email_to_user else False


def test():
    print(get_member_list())

    for m in fetch_members():
        if m["days_left"] > 0:
            print(m)


if __name__ == "__main__":
    test()
