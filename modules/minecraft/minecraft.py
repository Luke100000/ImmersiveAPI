import os
from functools import cache

import requests
from databases import Database

from main import Configurator

HAGRID_SECRET = os.getenv("HAGRID_SECRET")


# Open Database
@cache
def get_database():
    return Database("sqlite:///cache/hagrid.db")


async def setup():
    await get_database().execute(
        "CREATE TABLE IF NOT EXISTS users (oid INTEGER PRIMARY KEY AUTOINCREMENT, guild INTEGER, discord_id INTEGER, discord_username CHAR, minecraft_username CHAR, minecraft_uuid CHAR, roles CHAR)"
    )
    await get_database().execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS primary_index on users (guild, discord_id)"
    )
    await get_database().execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS minecraft_username on users (guild, minecraft_username)"
    )
    await get_database().execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS minecraft_uuid on users (guild, minecraft_uuid)"
    )


def get_uuid(username: str):
    response = requests.get(
        f"https://api.mojang.com/users/profiles/minecraft/{username}"
    )
    data = response.json()
    return data["id"] if "id" in data else None


def init(configurator: Configurator):
    configurator.register("Minecraft", "Server authentication using the ArchLink mod.")
    
    @configurator.app.on_event("startup")
    async def _startup():
        await get_database().connect()
        await setup()

    def pack(user):
        return {
            "id": user["oid"],
            "guild": user["guild"],
            "discord_username": user["discord_username"],
            "minecraft_username": user["minecraft_username"],
            "minecraft_uuid": user["minecraft_uuid"],
            "roles": user["roles"],
        }

    @configurator.get("/v1/minecraft/{guild}")
    async def get_all_users(guild: int):
        users = await get_database().fetch_all(
            "SELECT * FROM users WHERE guild = :guild",
            {"guild": guild},
        )
        return [pack(u) for u in users]

    @configurator.get("/v1/minecraft/{guild}/{identifier}")
    async def get_user(guild: int, identifier: str):
        user = await get_database().fetch_one(
            "SELECT * FROM users WHERE guild = :guild AND (minecraft_username = :identifier OR minecraft_uuid = :identifier)",
            {
                "guild": guild,
                "identifier": identifier,
            },
        )
        if user is None:
            return {"error": "Username not linked."}
        else:
            return pack(user)

    @configurator.delete("/v1/minecraft/{guild}/{username}")
    async def delete_user(guild: int, username: str):
        user = await get_database().execute(
            "DELETE FROM users WHERE guild = :guild AND (minecraft_username = :username OR discord_id = :username)",
            {
                "guild": guild,
                "username": username,
            },
        )
        if user == 0:
            return {"error": "No user found."}
        else:
            return {}

    @configurator.post("/v1/minecraft/{guild}/{discord_id}")
    async def post_user(
        guild: int,
        discord_id: int,
        token: str,
        discord_username: str,
        minecraft_username: str,
        roles: str,
    ):
        if token != HAGRID_SECRET:
            return {"error", "Permission denied."}

        if await get_database().fetch_one(
            "SELECT * FROM users WHERE guild = :guild AND minecraft_username = :minecraft_username",
            {"guild": guild, "minecraft_username": minecraft_username},
        ):
            return {"error": "Minecraft account already linked."}

        if await get_database().fetch_one(
            "SELECT * FROM users WHERE guild = :guild AND discord_id = :discord_id",
            {"guild": guild, "discord_id": discord_id},
        ):
            return {"error": "Discord account already linked."}

        uuid = get_uuid(minecraft_username)

        if uuid is None:
            return {"error": "Minecraft account does not exist."}

        await get_database().execute(
            """
            INSERT INTO users(guild, discord_id, discord_username, minecraft_username, minecraft_uuid, roles)
                VALUES(:guild, :discord_id, :discord_username, :minecraft_username, :minecraft_uuid, :roles)
            """,
            {
                "guild": guild,
                "discord_id": discord_id,
                "discord_username": discord_username,
                "minecraft_username": minecraft_username,
                "minecraft_uuid": uuid,
                "roles": roles,
            },
        )
        return {}

    @configurator.put("/v1/minecraft/{guild}/{discord_id}")
    async def put_user(
        guild: int,
        discord_id: int,
        token: str,
        discord_username: str,
        roles: str,
    ):
        if token != HAGRID_SECRET:
            return {"error", "Permission denied."}

        affected = await get_database().execute(
            """
            UPDATE users
            SET discord_username = :discord_username, roles = :roles
            WHERE guild = :guild AND discord_id = :discord_id
            """,
            {
                "guild": guild,
                "discord_id": discord_id,
                "discord_username": discord_username,
                "roles": roles,
            },
        )

        return {} if affected > 0 else {"error", "No member found."}
