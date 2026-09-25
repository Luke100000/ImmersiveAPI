import asyncio
import os
import time

import requests
from crowdin_api import CrowdinClient
from crowdin_api.api_resources.reports.enums import Format, Unit
from crowdin_api.exceptions import NotFound
from loguru import logger

TRANSLATOR_CACHE_TTL_SECONDS = 24 * 60 * 60
TRANSLATOR_MIN_ACTIONS = 10
IGNORED_TRANSLATOR_USERNAMES = {"Luke100000", "REMOVED_USER"}

_translator_names: list[str] = []
_translator_names_refreshed_at: float | None = None
_translator_refresh_task: asyncio.Task[None] | None = None


class MCACrowdinClient(CrowdinClient):
    TOKEN = os.getenv("CROWDIN_KEY")
    PROJECT_ID = 456324
    TIMEOUT = 60


def extract_translator_names(report: dict) -> list[str]:
    names = []
    for member in report["data"]:
        actions = member["translated"] + member["approved"] + member["voted"]
        if actions <= TRANSLATOR_MIN_ACTIONS:
            continue
        username = member["user"]["username"]
        if username in IGNORED_TRANSLATOR_USERNAMES:
            continue

        names.append(username)

    return names


def fetch_translator_names() -> list[str]:
    client = MCACrowdinClient()
    report_request = client.reports.generate_top_members_report(
        unit=Unit.WORDS,
        format=Format.JSON,
    )
    identifier = report_request["data"]["identifier"]

    while True:
        try:
            report = client.reports.download_report(identifier)
            break
        except NotFound:
            time.sleep(1)

    response = requests.get(report["data"]["url"], timeout=60)
    response.raise_for_status()
    return extract_translator_names(response.json())


async def refresh_translator_names():
    global _translator_names, _translator_names_refreshed_at

    # noinspection PyBroadException
    try:
        names = await asyncio.to_thread(fetch_translator_names)
    except Exception:
        logger.exception("Failed to refresh Crowdin translator names")
        return

    _translator_names = names
    _translator_names_refreshed_at = time.monotonic()


async def get_cached_translator_names() -> list[str]:
    global _translator_refresh_task

    cache_expired = (
        _translator_names_refreshed_at is None
        or time.monotonic() - _translator_names_refreshed_at
        >= TRANSLATOR_CACHE_TTL_SECONDS
    )
    if cache_expired and (
        _translator_refresh_task is None or _translator_refresh_task.done()
    ):
        _translator_refresh_task = asyncio.create_task(refresh_translator_names())

    return _translator_names.copy()
