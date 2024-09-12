import os
import shutil
import uuid
from typing import Optional

import aiofiles
from fastapi import Request
from starlette.responses import Response
from starlette.templating import Jinja2Templates

from common.utils import fetch_file
from main import Configurator
from modules.converter.registry import clean_format, conversions


def init(configurator: Configurator):
    configurator.register("Converter", "Converts between different formats.")

    templates = Jinja2Templates(directory="modules/converter/templates")

    temp_dir = "temp/conversions"

    shutil.rmtree(temp_dir, ignore_errors=True)
    os.makedirs(temp_dir, exist_ok=True)

    @configurator.get("/convert/{output_format}")
    async def index(request: Request, output_format: str = "png"):
        return templates.TemplateResponse(
            "index.html", {"request": request, "id": id, "output_format": output_format}
        )

    @configurator.get("/v1/convert/{to_format}")
    @configurator.post("/v1/convert/{to_format}")
    async def convert(
        request: Request,
        to_format: Optional[str] = None,
        from_format: Optional[str] = None,
        url: Optional[str] = None,
    ):
        from_format = clean_format(str(from_format))
        to_format = clean_format(to_format)

        temp_name = uuid.uuid4().hex
        in_file = f"{temp_dir}/in.{temp_name}.{from_format}"
        out_file = f"{temp_dir}/out.{temp_name}.{to_format}"

        try:
            if url is None:
                async with aiofiles.open(in_file, "wb") as file:
                    await file.write(await request.body())
            else:
                await fetch_file(url, in_file)

            converters = conversions[str(from_format)][to_format]

            if len(converters) == 0:
                return Response("No matching converter", status_code=400)

            converter = next(iter(converters.values()))
            await converter(in_file, out_file, from_format, to_format)

            try:
                with open(out_file, "rb") as file:
                    return Response(content=file.read(), media_type="image")
            except FileNotFoundError:
                return Response("Converter provided no output.", status_code=400)
        finally:
            try:
                os.remove(in_file)
            except FileNotFoundError:
                pass
            try:
                os.remove(out_file)
            except FileNotFoundError:
                pass
