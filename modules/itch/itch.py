import os

import itchio
from cachetools import TTLCache, cached

from main import Configurator


def init(configurator: Configurator):
    configurator.register("Itch", "Proxy for the Itch.io API to list projects.")

    @cached(TTLCache(maxsize=1, ttl=86400))
    def get_games() -> list:
        apikey = os.getenv("ITCHIO_API_KEY")
        if apikey:
            session = itchio.Session(apikey)
        else:
            raise ValueError("ITCHIO_API_KEY is not set.")

        games = []
        for game in itchio.GameCollection(session).all():
            available = game.p_windows or game.p_osx or game.p_linux or game.p_android
            if available and game.published:
                games.append(
                    {
                        "id": game.id,
                        "title": game.title,
                        "short_text": game.short_text,
                        "url": game.url,
                        "published_at": game.published_at,
                        "downloads_count": game.downloads_count,
                        "views_count": game.views_count,
                        "cover_url": game.cover_url,
                        "p_windows": game.p_windows,
                        "p_osx": game.p_osx,
                        "p_linux": game.p_linux,
                        "p_android": game.p_android,
                    }
                )

        games.sort(key=lambda x: x["downloads_count"], reverse=True)

        return games

    @configurator.get("/v1/itchio")
    def get_itchio():
        return get_games()

    return [get_itchio]
