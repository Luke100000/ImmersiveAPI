import time
from datetime import datetime, timezone
from typing import Optional

import ciso8601
import requests
from packaging.version import InvalidVersion, Version


def request_get(
    *args, default_wait_time: int = 5, max_retries: int = 5, **kwargs
) -> Optional[requests.Response]:
    response = None
    for attempt in range(max_retries):
        response = requests.get(*args, **kwargs)
        if response.status_code == 429:
            wait_time = int(response.headers.get("Retry-After", default_wait_time))
            print(
                f"Rate limit hit, sleeping for {wait_time} seconds (Attempt {attempt + 1}/{max_retries})"
            )
            time.sleep(wait_time)
        elif response.status_code >= 400:
            print("Forbidden, maybe rate limited, lets sleep a while...")
            time.sleep(60)
        else:
            return response
    return response


def date_to_timestamp(date_str: str) -> int:
    """
    Converts a date string to a timestamp.
    """
    return int(ciso8601.parse_datetime(date_str).timestamp())


def age_in_days(timestamp: int) -> int:
    """
    Converts a date string to a datetime object and calculates the age of the file in days.
    """
    # Convert the string to a datetime object
    file_date = datetime.fromtimestamp(timestamp, timezone.utc)

    # Get the current datetime
    current_date = datetime.now(timezone.utc)

    # Calculate the difference in days
    return max(1, (current_date - file_date).days + 1)


def to_version(version: str) -> Optional[Version]:
    try:
        return Version(version)
    except InvalidVersion:
        return None


def parse_versions(versions: list[str]) -> list[str]:
    rv = [to_version(version) for version in versions]
    s = sorted([version for version in rv if version])
    return [str(version) for version in s]


def is_clean_version(version: str) -> bool:
    parts = version.split(".")
    while len(parts) < 3:
        parts.append("0")

    try:
        for part in parts:
            int(part)
    except ValueError:
        return False

    return len(parts) == 3
