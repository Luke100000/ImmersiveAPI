import os
import shutil
import uuid

import aiofile
import aiohttp
from dotenv import load_dotenv
from starlette.responses import Response

from converter import conversions, file_formats
from converters.abc2midi import install_abc2midi
from converters.ffmpeg import install_ffmpeg
from converters.imagemagick import install_imagemagick
from converters.opencv import install_opencv
from converters.pillow import install_pillow

load_dotenv()

from prometheus_client import CollectorRegistry, multiprocess

# Setup prometheus for multiprocessing
prom_dir = os.environ["PROMETHEUS_MULTIPROC_DIR"]
shutil.rmtree(prom_dir, ignore_errors=True)
os.makedirs(prom_dir, exist_ok=True)
registry = CollectorRegistry()
multiprocess.MultiProcessCollector(registry)

from fastapi import FastAPI, Request
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI()

shutil.rmtree("temp", ignore_errors=True)
os.makedirs("temp", exist_ok=True)

# Prometheus integration
instrumentator = Instrumentator().instrument(app)


async def fetch_file(url, target):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            assert resp.status == 200
            data = await resp.read()

        async with aiofile.async_open(target, "wb") as outfile:
            await outfile.write(data)


@app.on_event("startup")
async def _startup():
    instrumentator.expose(app)


install_abc2midi()
install_ffmpeg()
install_imagemagick()
install_opencv()
install_pillow()


@app.get("/v1/convert/")
async def fetch_list():
    sorted_file_formats = sorted(file_formats)
    header = (
        "<tr><td></td>"
        + " ".join(
            [
                f"<td style='writing-mode: vertical-lr; text-align: right'>{f}</td>"
                for f in sorted_file_formats
            ]
        )
        + "</tr>"
    )

    data = header + "\n"
    for first_format in sorted_file_formats:
        data += f"<tr><td style='text-align: right'>{first_format}</td>"
        for second_format in sorted_file_formats:
            converters = conversions[first_format][second_format]
            f = "green-square" if len(converters) > 0 else "red-square"
            tooltip = f"Supported by {len(converters)} converters."
            data += f"<td class='{f}' title='{tooltip}'></td>"
        data += "</tr>\n"

    page = (
        """
            <!DOCTYPE html>
            <html lang="en-us">
            <head>
            <style>
              .red-square {
                width: 20px;
                height: 20px;
                background-color: red;
              }
              
              .orange-square {
                width: 20px;
                height: 20px;
                background-color: orange;
              }
              
              .green-square {
                width: 20px;
                height: 20px;
                background-color: green;
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
@app.get("/v1/convert/{to_format}")
async def convert(
    request: Request, to_format: str = None, from_format: str = None, url: str = None
):
    from_format = str(from_format)

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

    await next(iter(converters))(request, from_format, from_format, to_format)

    with open(out_file, "rb") as file:
        return Response(content=file.read(), media_type="image")


print(f"{len(file_formats)} formats loaded")
