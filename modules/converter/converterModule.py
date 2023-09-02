import json
import os
import shutil
import uuid

from fastapi import FastAPI, Request
from starlette.responses import Response
from starlette.templating import Jinja2Templates

from modules.converter.converter import conversions, file_formats, clean_format
from modules.converter.converters.abc2midi import install_abc2midi
from modules.converter.converters.ffmpeg import install_ffmpeg
from modules.converter.converters.imagemagick import install_imagemagick
from modules.converter.converters.opencv import install_opencv
from modules.converter.converters.pillow import install_pillow
from utils import fetch_file

templates = Jinja2Templates(directory="modules/converter/templates")

temp_dir = "temp_conversion"

shutil.rmtree(temp_dir, ignore_errors=True)
os.makedirs(temp_dir, exist_ok=True)

if os.path.exists("modules/converter/test/results.json"):
    with open("modules/converter/test/results.json") as results_file:
        recommended_converter = json.load(results_file)
else:
    recommended_converter = {}


install_abc2midi()
install_ffmpeg()
install_imagemagick()
install_opencv()
install_pillow()


def initConverterModule(app: FastAPI):
    @app.get("/convert")
    async def index(request: Request):
        return templates.TemplateResponse("index.html", {"request": request, "id": id})

    @app.get("/v1/convert/{to_format}")
    @app.post("/v1/convert/{to_format}")
    async def convert(
        request: Request,
        to_format: str = None,
        from_format: str = None,
        url: str = None,
    ):
        from_format = clean_format(str(from_format))
        to_format = clean_format(to_format)

        temp_name = uuid.uuid4().hex
        in_file = f"{temp_dir}/in.{temp_name}.{from_format}"
        out_file = f"{temp_dir}/out.{temp_name}.{to_format}"

        try:
            if url is None:
                with open(in_file, "wb") as file:
                    file.write(await request.body())
            else:
                await fetch_file(url, in_file)

            converters = conversions[str(from_format)][to_format]

            if len(converters) == 0:
                return Response("No matching converter", status_code=400)

            recommended = (
                recommended_converter[from_format][to_format]
                if (
                    from_format in recommended_converter
                    and to_format in recommended_converter[from_format]
                )
                else None
            )
            converter = (
                next(iter(converters.values()))
                if recommended is None
                else converters[recommended]
            )
            await converter(in_file, out_file, from_format, to_format)

            with open(out_file, "rb") as file:
                return Response(content=file.read(), media_type="image")
        finally:
            try:
                os.remove(in_file)
            except FileNotFoundError:
                pass
            try:
                os.remove(out_file)
            except FileNotFoundError:
                pass

    print(f"{len(file_formats)} formats loaded")
