import os

import itchio
from fastapi import FastAPI

key = os.getenv("ITCHIO_API_KEY")

session = itchio.Session(key)

games = []
for game in itchio.GameCollection(session).all():
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
        }
    )

print(games)


def itchioModule(app: FastAPI):
    @app.get("/v1/itchio")
    def get_patrons():
        return games
