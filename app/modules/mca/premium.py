import dbm.dumb
import os
import shelve
from datetime import datetime, timedelta

from app.utils import get_cache_path

os.makedirs("cache", exist_ok=True)


class PremiumManager:
    def __init__(self):
        self.db = shelve.Shelf(
            dbm.dumb.open(get_cache_path("premium_data"), "c"), writeback=True
        )

    def __del__(self):
        self.db.close()

    def set_premium(self, username: str, days: int):
        expiration_date = datetime.now() + timedelta(days=days)
        self.db[username] = expiration_date
        self.db.sync()

    def is_premium(self, username: str):
        if username in self.db:
            expiration_date = self.db[username]
            return expiration_date > datetime.now()
        else:
            return False
