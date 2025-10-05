import os

from .database import ModDatabase

os.makedirs("cache", exist_ok=True)

database = ModDatabase()
