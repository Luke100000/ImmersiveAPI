from collections import defaultdict
from typing import Callable

conversions: dict[str, dict[str, dict[str, Callable]]] = defaultdict(
    lambda: defaultdict(dict)
)
file_formats = set()


def clean_format(f):
    return f.replace(".", "").lower()


def add_converter(from_formats: set, to_formats: set, converter: Callable, name: str):
    for from_format in {"none"}.union(from_formats):
        from_format = clean_format(from_format)
        for to_format in to_formats:
            to_format = clean_format(to_format)
            conversions[from_format][to_format][name] = converter
            file_formats.add(from_format)
            file_formats.add(to_format)
