import os

from modules.mc_version_stats.database import ModDatabase

os.makedirs("cache", exist_ok=True)

database = ModDatabase()
