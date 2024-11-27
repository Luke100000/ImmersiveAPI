import json
from typing import List, Dict, Any, Optional, Generator

from modules.mc_version_stats.mod import Mod
from modules.mc_version_stats.utils import (
    request_get,
    date_to_timestamp,
    parse_versions,
)

PAGE_SIZE = 100


def modrinth_search(
    query: Optional[str] = None,
    facets: Optional[List[List[str]]] = None,
    index: Optional[str] = None,
    offset: Optional[int] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Searches for projects on Modrinth.

    Parameters:
    - query (str): The search query string.
    - facets (Optional[List[List[str]]]): Facets to filter the search results.
    - index (Optional[str]): The index to sort by.
    - offset (Optional[int]): The number of results to skip.
    - limit (Optional[int]): The number of results to return.

    Returns:
    - Dict[str, Any]: The search results from the Modrinth API.
    """
    url = "https://api.modrinth.com/v2/search"
    params = {
        "query": query,
        "facets": json.dumps(facets) if facets is not None else None,
        "index": index,
        "offset": offset,
        "limit": limit,
    }

    # Filter out None values
    params = {k: v for k, v in params.items() if v is not None}

    response = request_get(url, params=params)
    if not response:
        raise Exception("Failed to get response from Modrinth API")
    response.raise_for_status()
    return response.json()


blacklisted_categories = {
    "any",
    "forge",
    "cauldron",
    "liteloader",
    "fabric",
    "quilt",
    "neoforge",
    "client",
    "server",
}


def prepare_categories(categories: list[str]) -> set[str]:
    return {
        category.lower()
        for category in categories
        if category not in blacklisted_categories
    }


def populate_modrinth_details(mod: Mod) -> Mod:
    response = request_get(f"https://api.modrinth.com/v2/project/{mod.id}")
    if not response:
        raise Exception("Failed to get response from Modrinth API")
    response.raise_for_status()
    result = response.json()

    mod.body = result["body"]
    mod.links = {
        "issues": result["issues_url"],
        "source": result["source_url"],
        "wiki": result["wiki_url"],
        "discord": result["discord_url"],
        **{d["id"]: d["url"] for d in result["donation_urls"]},
    }

    mod.mod_loaders = set(result["loaders"])

    return mod


def get_modrinth_mods(project_type: str = "mod") -> Generator[Mod, None, None]:
    index = 0
    while True:
        results = modrinth_search(
            limit=PAGE_SIZE,
            offset=index,
            facets=[
                ["project_type:" + project_type],
                ["downloads>100"],
            ],
            index="downloads",
        )["hits"]
        index += PAGE_SIZE

        if len(results) == 0:
            break

        for result in results:
            mod = Mod(
                id=result["project_id"],
                source="modrinth",
                slug=result["slug"],
                last_modified=date_to_timestamp(result["date_modified"]),
                created_at=date_to_timestamp(result["date_created"]),
                name=result["title"],
                author=result["author"],
                description=result["description"],
                type=result["project_type"],
                categories=prepare_categories(result["categories"]),
                downloads=result["downloads"],
                follows=result["follows"],
                body="",
                license=result["license"],
                links={},
                icon=result["icon_url"],
                gallery=result["gallery"],
                versions=parse_versions(result["versions"]),
            )

            if result["client_side"] == "required":
                mod.categories.add("client")
            if result["client_side"] == "optional":
                mod.categories.add("optional-client")
            if result["server_side"] == "required":
                mod.categories.add("server")

            if "featured_gallery" in result and result["featured_gallery"]:
                if result["featured_gallery"] in mod.gallery:
                    mod.gallery.remove(result["featured_gallery"])
                mod.gallery.insert(0, result["featured_gallery"])

            yield mod
