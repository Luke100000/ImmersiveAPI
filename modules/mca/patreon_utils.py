import os

import patreon
from dotenv import load_dotenv

load_dotenv()

# Authentication
api_client = patreon.API(os.getenv("PATREON_API_KEY"))


async def verify_patron(email: str) -> bool:
    user_response = api_client.fetch_page_of_pledges("4491801", 100).json_data[
        "included"
    ]
    for u in user_response:
        if (
            u["type"] == "user"
            and u["attributes"]["email"].lower().strip() == email.lower().strip()
        ):
            return True
    return False
