from PIL import Image

from modules.converter.converter import add_converter


async def pillow_converter(
    in_file: str, out_file: str, in_format: str, out_format: str
):
    with Image.open(in_file) as img:
        img.save(out_file, format=out_format)


def install_pillow():
    extensions = Image.registered_extensions()
    readable_formats = {ex for ex, f in extensions.items() if f in Image.OPEN}
    savable_formats = {ex for ex, f in extensions.items() if f in Image.SAVE}

    add_converter(readable_formats, savable_formats, pillow_converter, "pillow")
