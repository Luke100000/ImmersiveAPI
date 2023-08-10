import asyncio
import subprocess

from converter import add_converter


async def ffmpeg_converter(
    in_file: str, out_file: str, in_format: str, out_format: str
):
    await (
        await asyncio.create_subprocess_exec("ffmpeg", "-i", in_file, out_file)
    ).wait()


def install_ffmpeg():
    process = subprocess.run(
        ["ffmpeg", "-formats"],
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    readable_formats = set()
    savable_formats = set()

    active = False
    for line in process.stdout.decode("utf-8").splitlines():
        if active:
            decode = line[1] == "D"
            encode = line[2] == "E"
            extension = line[4:16].strip()
            if decode:
                readable_formats.add(extension)
            if encode:
                savable_formats.add(extension)
        if line == " --":
            active = True

    add_converter(readable_formats, savable_formats, ffmpeg_converter)
