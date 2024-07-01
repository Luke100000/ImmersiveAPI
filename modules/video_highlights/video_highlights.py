from a2wsgi import WSGIMiddleware

from main import Configurator
from modules.video_highlights.dashboard import get_app


def init(configurator: Configurator):
    configurator.register(
        "Video Highlight Extractor",
        "Extracts prompted key moments from video material.",
    )

    # noinspection PyTypeChecker
    configurator.app.mount(
        "/highlights", WSGIMiddleware(get_app("/highlights/").server)
    )
