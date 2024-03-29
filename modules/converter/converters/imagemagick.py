import asyncio
import glob
import os
import subprocess


async def imagemagick_converter(
    in_file: str, out_file: str, in_format: str, out_format: str
):
    await (
        await asyncio.create_subprocess_exec(
            "convert", "-format", out_format, in_file, out_file
        )
    ).wait()

    for file in glob.glob("**.shtml"):
        os.remove(file)


def install_imagemagick(add_converter):
    process = subprocess.run(
        ["identify", "-list", "format"],
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    readable_formats = set()
    savable_formats = set()

    format_index = 0
    mode_index = 0

    active = False
    for line in process.stdout.decode("utf-8").splitlines():
        if active:
            if len(line) > mode_index + 1:
                decode = line[mode_index] == "r"
                encode = line[mode_index + 1] == "w"
                extension = line[: format_index + 1].strip().replace("*", "")
                if extension:
                    if decode:
                        readable_formats.add(extension)
                    if encode:
                        savable_formats.add(extension)
        elif line.startswith("--------"):
            active = True
        else:
            format_index = line.find("Format") + 5
            mode_index = line.find("Mode")

    add_converter(
        readable_formats, savable_formats, imagemagick_converter, "imagemagick"
    )
