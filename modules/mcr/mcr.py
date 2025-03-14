from fastapi import FastAPI

from main import Configurator

from minecraft_recipe_renderer.api import setup as setup_renderer


def init(configurator: Configurator):
    configurator.register(
        "Minecraft Recipe Renderer", "Render Minecraft recipes to images."
    )

    sub_app = FastAPI()
    configurator.app.mount("/mcr", sub_app)

    setup_renderer(sub_app)
