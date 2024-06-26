import time
from datetime import datetime, timezone

import ciso8601
import requests


def request_get(*args, default_wait_time: int = 5, max_retries: int = 5, **kwargs):
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


def age_in_days(date_str: str) -> int:
    """
    Converts a date string to a datetime object and calculates the age of the file in days.
    """
    # Convert the string to a datetime object
    file_date = ciso8601.parse_datetime(date_str)

    # Get the current datetime
    current_date = datetime.now(timezone.utc)

    # Calculate the difference in days
    return max(1, (current_date - file_date).days + 1)
