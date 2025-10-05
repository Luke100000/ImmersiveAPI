import re
from dataclasses import dataclass
from typing import Optional

from bs4 import BeautifulSoup
from markdownify import MarkdownConverter


def _remove_unwanted_content(s: str) -> str:
    # Remove content in square brackets
    # noinspection RegExpRedundantEscape
    s = re.sub(r"\[.*?\]", "", s)
    # Remove code blocks enclosed in triple backticks
    s = re.sub(r"```.*?```", "", s, flags=re.DOTALL)
    return s


def _remove_spaces(s: str) -> str:
    while True:
        new = s.replace("\n\n\n", "\n\n")
        if new == s:
            break
        s = new
    return s


@dataclass
class Node:
    title: str
    level: int
    content: str
    children: list["Node"]
    parent: Optional["Node"]


DEFAULT_BLACKLIST = {
    "Contents",
    "Data values",
    "Issues",
    "Gallery",
    "References",
    "Navigation",
    "Navigation menu",
}


def _traverse(node: Node, blacklist: set[str], result: list[str] = None):
    if result is None:
        result = []

    if node.title not in blacklist:
        result.append("#" * node.level + " " + node.title + "\n" + node.content)

        for child in node.children:
            _traverse(child, blacklist, result)

    return result


def get_chapters(md: str) -> list[str]:
    current = Node("", 0, "", [], None)
    root = current

    for line in md.split("\n"):
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))

            for i in range(current.level - level + 1):
                current = current.parent

            if current is None:
                current = root

            current.children.append(
                Node(line.lstrip("#").strip(), level, "", [], current)
            )
            current = current.children[-1]
        else:
            current.content += line + "\n"

    return _traverse(
        root,
        DEFAULT_BLACKLIST,
    )


def filter_tree(md: str) -> str:
    return "\n".join(get_chapters(md))


def get_cleaned_content(html: str):
    """
    Remove links, code blocks, ...
    """
    soup = BeautifulSoup(html, "html.parser")
    md = MarkdownConverter(
        strip=["a", "img"],
        code_language_callback=lambda r: None,
        heading_style="ATX",
    ).convert_soup(soup)

    md = _remove_spaces(md)
    md = _remove_unwanted_content(md)
    md = filter_tree(md)
    md = md.strip()

    return md
