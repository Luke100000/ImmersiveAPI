import os
from datetime import datetime, timedelta
from math import ceil

import requests
from cachetools import TTLCache, cached
from dotenv import load_dotenv
from patreon.utils import user_agent_string

load_dotenv()

access_token = os.getenv("PATREON_API_KEY")
campaign_id = os.getenv("PATREON_CAMPAIGN_ID")

MONTHLY_SUBSCRIPTION_COST_CENTS = 400
FALLBACK_SUBSCRIPTION_DAYS = 30


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
                    "currently_entitled_amount_cents",
                    "last_charge_status",
                    "next_charge_date",
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

    return members


def legacy_days_left(member: dict) -> int:
    if member["patron_status"] == "active_patron":
        if "last_charge_date" in member and member["last_charge_date"]:
            date1 = datetime.strptime(
                member["last_charge_date"], "%Y-%m-%dT%H:%M:%S.%f%z"
            )
            date2 = datetime.now(date1.tzinfo)
            return max(0, 35 - (date2 - date1).days)
        return 35
    return 0


def is_active_subscription(member: dict) -> bool:
    return (
        member.get("patron_status") == "active_patron"
        and int(member.get("currently_entitled_amount_cents") or 0) > 0
    )


def parse_patreon_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def days_until(date: datetime) -> int:
    now = datetime.now(date.tzinfo)
    return max(1, ceil((date - now).total_seconds() / 86400))


def subscription_days_left(member: dict) -> int:
    if not is_active_subscription(member):
        return 0

    next_charge_date = parse_patreon_datetime(member.get("next_charge_date"))
    if next_charge_date:
        return days_until(next_charge_date)

    last_charge_date = parse_patreon_datetime(member.get("last_charge_date"))
    entitled_amount = int(member.get("currently_entitled_amount_cents") or 0)
    if last_charge_date and entitled_amount > 0:
        months_paid = entitled_amount / MONTHLY_SUBSCRIPTION_COST_CENTS
        estimated_expiration = last_charge_date + timedelta(
            days=FALLBACK_SUBSCRIPTION_DAYS * months_paid
        )
        if estimated_expiration > datetime.now(estimated_expiration.tzinfo):
            return days_until(estimated_expiration)

    return FALLBACK_SUBSCRIPTION_DAYS


def get_member_list():
    members = [m for m in fetch_members() if m["campaign_lifetime_support_cents"] > 0]
    sorted_members = sorted(
        members, key=lambda m: m["campaign_lifetime_support_cents"], reverse=True
    )
    return [m["full_name"] for m in sorted_members]


def verify_patron(email: str) -> int | bool:
    email = email.lower().strip()

    email_to_user = {
        m["email"].lower().strip(): m for m in fetch_members() if m["email"] is not None
    }

    return (
        subscription_days_left(email_to_user[email])
        if email in email_to_user
        else False
    )
