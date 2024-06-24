import os
import shelve
from functools import cache
from typing import List

from modules.mc_version_stats.mod import Mod

os.makedirs("cache", exist_ok=True)


@cache
def get_db():
    return shelve.open("cache/mods.db")


def get_cached_mods() -> List[Mod]:
    return list(get_db().values())
