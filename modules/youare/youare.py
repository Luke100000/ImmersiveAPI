import io

from PIL import Image, ImageDraw
from fastapi import FastAPI, Request
from geolite2 import geolite2
from starlette.responses import Response


def render_image(
    text,
    position=(10, 10),
    font_color=(40, 220, 50),
    bg_color=(49, 51, 56),
    size=(200, 76),
):
    # Create a blank image
    image = Image.new("RGB", size=size, color=bg_color)
    draw = ImageDraw.Draw(image)
    draw.text(position, text, fill=font_color)

    # Save the image to a byte buffer
    img_byte_array = io.BytesIO()
    image.save(img_byte_array, format="PNG")

    return img_byte_array.getvalue()


def initYouAre(app: FastAPI):
    geo = geolite2.reader()

    @app.get("/v1/you")
    def get_you(request: Request):
        x = geo.get(str(request.client.host))
        if x is None:
            text = "Hmm, I can't see you."
        else:
            city = x["city"]["names"]["en"]
            continent = x["continent"]["names"]["en"]
            country = x["country"]["names"]["en"]
            text = (
                f"I see you!\nCity: {city}\nContinent: {continent}\nCountry: {country}"
            )
        image = render_image(text)
        return Response(content=image, media_type="image/png")
