import asyncio

from converter import add_converter


async def abc2midi_converter(
    in_file: str, out_file: str, in_format: str, out_format: str
):
    await (await asyncio.create_subprocess_exec("abc2midi", in_file, "-o", out_file)).wait()


def install_abc2midi():
    add_converter({"abc"}, {"midi", "mid"}, abc2midi_converter, "abc2midi")
