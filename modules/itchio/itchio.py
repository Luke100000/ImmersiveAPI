import os

import itchio
from fastapi import FastAPI


def initItchIo(app: FastAPI):
    key = os.getenv("ITCHIO_API_KEY")

    session = itchio.Session(key)

    games = []
    for game in itchio.GameCollection(session).all():
        available = game.p_windows or game.p_osx or game.p_linux or game.p_android
        if available:
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

    @app.get("/v1/itchio")
    def get_itchio():
        return games
