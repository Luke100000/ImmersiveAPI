import gzip
import logging
import os
from io import BytesIO

import diskcache
import requests

os.makedirs("cache", exist_ok=True)

cache = diskcache.Cache("cache/requests.cache")


def _compress(s: bytes) -> bytes:
    with BytesIO() as buffer:
        with gzip.GzipFile(fileobj=buffer, mode="wb") as f:
            f.write(s)
        return buffer.getvalue()


def _decompress(b: bytes) -> bytes:
    with BytesIO(b) as buffer:
        with gzip.GzipFile(fileobj=buffer, mode="rb") as f:
            return f.read()


def cached_request(url: str, lastmod: str) -> bytes:
    content, cached_last_mod = cache.get(url, default=(None, None))
    if content and cached_last_mod == lastmod:
        return _decompress(content)

    logging.info(f"Downloading {url}app.")
    response = requests.get(url)

    try:
        response.raise_for_status()
        content = response.content
    except requests.exceptions.HTTPError as e:
        logging.error(f"Error downloading {url}: {e}")
        content = b""

    cache.set(url, (_compress(content), lastmod))
    return content
