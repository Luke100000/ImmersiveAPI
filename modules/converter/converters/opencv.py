from PIL import Image

from modules.converter.converter import add_converter


async def opencv_converter(
    in_file: str, out_file: str, in_format: str, out_format: str
):
    with Image.open(in_file) as img:
        img.save(out_file, format=out_format)


def install_opencv():
    formats = {
        "bmp",
        "dib",
        "jpeg",
        "jpg",
        "jpe",
        "jp2",
        "png",
        "webp",
        "avif",
        "pbm",
        "pgm",
        "ppm",
        "pxm",
        "pnm",
        "pfm",
        "sr",
        "ras",
        "tiff",
        "tif",
        "exr",
        "hdr",
        "pic",
    }

    add_converter(formats, formats, opencv_converter, "opencv")
