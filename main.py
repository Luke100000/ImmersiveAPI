import json
import os
import shutil
from fastapi.templating import Jinja2Templates

from prometheus_client import CollectorRegistry, multiprocess
from starlette.middleware.gzip import GZipMiddleware

# Setup prometheus for multiprocessing
prom_dir = (
    os.environ["PROMETHEUS_MULTIPROC_DIR"]
    if "PROMETHEUS_MULTIPROC_DIR" in os.environ
    else None
)
if prom_dir is not None:
    shutil.rmtree(prom_dir, ignore_errors=True)
    os.makedirs(prom_dir, exist_ok=True)
    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)

import uuid
from typing import Any

import aiofile
import aiohttp
import orjson
from fastapi_cache.coder import Coder
from starlette.responses import Response

from converter import conversions, file_formats, clean_format
from converters.abc2midi import install_abc2midi
from converters.ffmpeg import install_ffmpeg
from converters.imagemagick import install_imagemagick
from converters.opencv import install_opencv
from converters.pillow import install_pillow
from fastapi import FastAPI, Request
from prometheus_fastapi_instrumentator import Instrumentator

shutil.rmtree("temp", ignore_errors=True)
os.makedirs("temp", exist_ok=True)

app = FastAPI()

app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=6)

# Prometheus integration
instrumentator = Instrumentator().instrument(app)

if os.path.exists("test/results.json"):
    with open("test/results.json") as results_file:
        recommended_converter = json.load(results_file)

templates = Jinja2Templates(directory="templates")


async def fetch_file(url, target):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            assert resp.status == 200
            data = await resp.read()

        async with aiofile.async_open(target, "wb") as outfile:
            await outfile.write(data)


install_abc2midi()
install_ffmpeg()
install_imagemagick()
install_opencv()
install_pillow()


@app.on_event("startup")
async def startup():
    instrumentator.expose(app)


class ORJsonCoder(Coder):
    @classmethod
    def encode(cls, value: Any) -> bytes:
        return orjson.dumps(value, default=vars)

    @classmethod
    def decode(cls, value: bytes) -> Any:
        return Response(value, media_type="application/json")


class BytesCoder(Coder):
    @classmethod
    def encode(cls, value: Any) -> bytes:
        return value.body

    @classmethod
    def decode(cls, value: bytes) -> Any:
        return Response(value)


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "id": id})


@app.get("/v1/formats/")
async def fetch_formats():
    sorted_file_formats = sorted(file_formats)
    header = (
        "<tr><td></td>"
        + " ".join([f"<td class='v'>{f}</td>" for f in sorted_file_formats])
        + "</tr>"
    )

    data = header + "\n"
    for first_format in sorted_file_formats:
        data += f"<tr><td style='text-align: right'>{first_format}</td>"
        for second_format in sorted_file_formats:
            converters = conversions[first_format][second_format]
            recommended = recommended_converter[first_format][second_format]
            f = (
                ("orange" if recommended is None else "green")
                if len(converters) > 0
                else "red"
            )
            tooltip = f"{len(converters)} converters."
            data += f"<td class='{f}' title='{tooltip}'></td>"
        data += "</tr>\n"

    page = (
        """
            <!DOCTYPE html>
            <html lang="en-us">
            <head>
            <style>
              .red {
                width: 20px;
                height: 20px;
                background-color: red;
              }
              
              .orange {
                width: 20px;
                height: 20px;
                background-color: orange;
              }
              
              .green {
                width: 20px;
                height: 20px;
                background-color: green;
              }
              
              .v {
                 writing-mode: vertical-lr;
                 text-align: right;
               }
            </style>
            <title>Supported Formats</title>
            </head>
            <body>
            
            <table>
            """
        + data
        + """
        </table>
        
        </body>
        </html>
    """
    )
    return Response(page)


@app.get("/v1/convert/{to_format}")
@app.post("/v1/convert/{to_format}")
async def convert(
    request: Request, to_format: str = None, from_format: str = None, url: str = None
):
    from_format = clean_format(str(from_format))
    to_format = clean_format(to_format)

    temp_name = uuid.uuid4().hex
    in_file = f"temp/in.{temp_name}.{from_format}"
    out_file = f"temp/out.{temp_name}.{to_format}"

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


print(f"{len(file_formats)} formats loaded")
