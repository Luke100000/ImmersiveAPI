from collections import defaultdict
from typing import Callable, Set

conversions: dict[str, dict[str, Set[Callable]]] = defaultdict(lambda: defaultdict(set))
file_formats = set()


def clean_format(f):
    return f.replace(".", "").lower()


def add_converter(from_formats: set, to_formats: set, converter: Callable):
    for from_format in from_formats:
        from_format = clean_format(from_format)
        for to_format in to_formats:
            to_format = clean_format(to_format)
            conversions[from_format][to_format].add(converter)
            file_formats.add(from_format)
            file_formats.add(to_format)
