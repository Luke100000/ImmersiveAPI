from pathlib import Path
from typing import Optional, TypeVar

import aiofiles
import aiohttp


async def fetch_file(url, target):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            assert resp.status == 200
            data = await resp.read()

        async with aiofiles.open(target, "wb") as outfile:
            await outfile.write(data)


T = TypeVar("T")


def not_none(x: Optional[T]) -> T:
    if x is None:
        raise ValueError("Value is None")
    return x


root = Path(__file__).parent.parent


def get_data_path(path: str) -> Path:
    return root / "data" / path


def get_cache_path(path: str) -> Path:
    return root / "cache" / path
