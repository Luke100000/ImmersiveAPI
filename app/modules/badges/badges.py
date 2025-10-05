import asyncio
import io
import textwrap
from io import BytesIO
from typing import Optional, Union
from urllib.parse import urlparse

import requests
from fastapi import Query
from fastapi_cache import Coder
from fastapi_cache.decorator import cache
from PIL import Image, ImageDraw, ImageFont
from starlette.responses import Response

from app.configurator import Configurator


class BytesCoder(Coder):
    @classmethod
    def encode(cls, value: bytes) -> bytes:
        return value

    @classmethod
    def decode(cls, value: bytes) -> bytes:
        return value


def encode_image(texture: Image.Image) -> bytes:
    buffer = io.BytesIO()
    texture.save(buffer, format="PNG")
    return buffer.getvalue()


def is_external_url(url):
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and parsed.hostname not in (
        "localhost",
        "127.0.0.1",
        "::1",
    )


def fitted_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_path: str,
    x: float,
    y: float,
    width: float,
    height: float,
    size: float,
    color: Union[int, str],
    anchor: Optional[str] = None,
):
    while True:
        if anchor is None:
            text = "\n".join(
                textwrap.wrap(
                    text,
                    width=int(width / size * 2.25),
                )
            )

        font = ImageFont.truetype(font_path, size)
        x0, y0, x1, y1 = draw.textbbox((0, 0), text, font=font)
        w = x1 - x0
        h = y1 - y0

        if size < 5 or (h < height and w < width):
            draw.text(
                (x, y),
                text,
                font=font,
                fill=color,
                anchor=anchor,
                spacing=2,
            )
            break
        size -= 1


def render_embed(
    title: str,
    description: str,
    icon_url: str,
    width: int = 400,
    height: int = 100,
    corner: int = 16,
    title_size: int = -1,
    scale: int = 4,
    border: int = 3,
    font: str = "data/Roboto-Regular.ttf",
    title_color: str = "#FFFFFF",
    description_color: str = "#C8C8C8",
    background_color: str = "#2C2C2C",
) -> bytes:
    if not is_external_url(icon_url):
        raise ValueError("Icon URL must be an external URL.")

    if title_size <= 0:
        title_size = height // 4

    # Create an image with dark gray background
    img = Image.new("RGBA", (width * scale, height * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw pill-shaped background with shadow
    draw.rounded_rectangle(
        [(0, 0), (width * scale, height * scale)],
        corner * scale,
        fill=background_color,
    )

    # Load and draw icon in pill shape
    try:
        response = requests.get(icon_url)
        icon_height = height - border * 2
        icon = (
            Image.open(BytesIO(response.content))
            .convert("RGBA")
            .resize((icon_height * scale, icon_height * scale))
        )
        icon_mask = Image.new("L", (icon_height * scale, icon_height * scale), 0)
        draw_icon = ImageDraw.Draw(icon_mask)
        draw_icon.rounded_rectangle(
            [
                (0, 0),
                (icon_height * scale, icon_height * scale),
            ],
            (corner - border) * scale,
            fill=255,
        )
        img.paste(icon, (border * scale, border * scale), icon_mask)
    except Exception:
        pass

    # Downscale to final resolution for anti-aliasing
    img = img.resize((width, height), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(img)

    # Title
    fitted_text(
        draw,
        title,
        font,
        height + 5,
        height * 0.3,
        width - height - 10,
        height * 0.3 - 5,
        title_size,
        title_color,
        "ls",
    )

    # Description
    fitted_text(
        draw,
        description,
        font,
        height + 5,
        height * 0.3 + 5,
        width - height - 10,
        height * 0.7 - 15,
        int(title_size * 0.75),
        description_color,
    )

    return encode_image(img)


@cache(expire=86400, coder=BytesCoder)
async def cached_render_embed(
    **kwargs,
) -> bytes:
    return await asyncio.to_thread(render_embed, **kwargs)


def init(configurator: Configurator):
    configurator.register("Asset Generator", "Misc Assets for websites and co.")

    # TODO: Bad path naming
    @configurator.get(
        "/embed",
        responses={200: {"content": {"image/png": {}}}},
    )
    async def get_embed(
        title: str = Query(
            title="Title",
            description="The title of the embed.",
        ),
        description: str = Query(
            title="Description",
            description="The content or description of the embed.",
        ),
        icon_url: str = Query(title="Icon", description="The URL to the icon."),
        width: int = Query(
            default=400,
            ge=100,
            le=500,
            title="Width",
            description="The width in pixels.",
        ),
        height: int = Query(
            default=100,
            ge=50,
            le=200,
            title="Height",
            description="The height in pixels.",
        ),
        background_color: str = Query(default="555555", title="Background Color"),
    ) -> Response:
        try:
            result = await cached_render_embed(
                title=title,
                description=description,
                icon_url=icon_url,
                width=width,
                height=height,
                background_color="#" + background_color,
            )
        except ValueError as e:
            return Response(status_code=422, content=str(e))

        return Response(
            content=result,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400, immutable"},
        )
