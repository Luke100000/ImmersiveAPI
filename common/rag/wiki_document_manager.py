import datetime
import gzip
import re
import traceback
import xml.etree.ElementTree as ElementTree
from io import BytesIO
from typing import List

from tqdm.auto import tqdm

from common.rag.cached_request import cached_request, cache
from common.rag.document_manager import DocumentManager, InformationPage, QualityPreset
from common.rag.html_processor import get_cleaned_content

whitelist = {"root", "Dungeons", "Earth", "Legends", "Story_Mode"}
blacklist = {
    "Edition",
    "Bedrock_Dedicated_Server",
    "Bedrock_Editor",
    "Launcher_",
    "/Blueprints",
    "MinecraftEdu_",
    "/Calculators",
    "/Mods",
    "/Tutorial",
    "disambiguation",
}

SUB_PAGES = False


def is_blacklisted(loc: str):
    for b in blacklist:
        if b in loc:
            return True
    return False


def is_version(loc: str):
    return re.fullmatch(r"[0-9.]*", loc.split("/")[-1]) is not None


def is_valid_location(loc: str):
    if not SUB_PAGES and loc.count("/") > 4:
        return False
    group = "root" if loc.count(":") == 1 else loc.split(":")[1]
    return group in whitelist and not is_blacklisted(loc) and not is_version(loc)


def download_and_extract_gz(url: str, lastmod: str):
    content = cached_request(url, lastmod)
    with gzip.GzipFile(fileobj=BytesIO(content)) as gz:
        return ElementTree.parse(gz).getroot()


def parse_sitemap_index(url: str, lastmod: str):
    root = ElementTree.fromstring(cached_request(url, lastmod))

    sitemap_index = []
    for sitemap in root:
        loc = sitemap.find("{http://www.sitemaps.org/schemas/sitemap/0.9}loc").text
        lastmod = sitemap.find(
            "{http://www.sitemaps.org/schemas/sitemap/0.9}lastmod"
        ).text
        sitemap_index.append((loc, lastmod))
    return sitemap_index


def parse_sitemap(url: str, lastmod: str):
    root = download_and_extract_gz(url, lastmod)
    urls = []
    for url_elem in root:
        loc = url_elem.find("{http://www.sitemaps.org/schemas/sitemap/0.9}loc").text
        lastmod = url_elem.find(
            "{http://www.sitemaps.org/schemas/sitemap/0.9}lastmod"
        ).text
        urls.append((loc, lastmod))
    return urls


def get_rounded_now():
    now = datetime.datetime.now()
    rounded_now = now.replace(minute=0, second=0, microsecond=0) + datetime.timedelta(
        hours=(now.minute // 30)
    )
    return rounded_now.strftime("%Y-%m-%d %H:%M:%S")


def fetch_content(index_url: str) -> dict[str, str]:
    sitemaps = parse_sitemap_index(index_url, get_rounded_now())
    for sitemap, lastmod in sitemaps:
        for loc, loc_lastmod in parse_sitemap(sitemap, lastmod):
            if is_valid_location(loc):
                content = cached_request(loc, loc_lastmod)
                yield loc, content


def _get_cached_cleaned_content(loc: str, content: str):
    cleaned_content = cache.get(loc + "_cleaned")
    if not cleaned_content:
        cleaned_content = get_cleaned_content(content)
        cache.set(loc + "_cleaned", cleaned_content)
    return cleaned_content


def _process_location(data):
    loc, content = data
    try:
        cleaned_content = _get_cached_cleaned_content(loc, content)
        return InformationPage.from_content(
            loc, cleaned_content, simplify=False, quality=QualityPreset.LOW
        )
    except Exception as e:
        print(f"Error processing {loc}: {e}")
        traceback.print_exc()


class WikiDocumentManager(DocumentManager):
    def __init__(
        self, index_url: str = "https://minecraft.wiki/images/sitemaps/index.xml"
    ):
        self.documents = [
            doc
            for doc in [
                _process_location(doc) for doc in tqdm(list(fetch_content(index_url)))
            ]
            if doc is not None
        ]

    def get_documents(self) -> List[InformationPage]:
        return self.documents
