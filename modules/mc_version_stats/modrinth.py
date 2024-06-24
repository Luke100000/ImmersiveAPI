import json
from typing import List, Dict, Any, Optional

from modules.mc_version_stats.mod import Version, Mod
from modules.mc_version_stats.utils import request_get

PAGE_SIZE = 100


def modrinth_search(
    query: str = None,
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
    response.raise_for_status()
    return response.json()


def get_project_versions(
    project_id: str,
    loaders: Optional[List[str]] = None,
    game_versions: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Retrieves the versions for a specific project on Modrinth.

    Parameters:
    - project_id (str): The ID of the project.
    - loaders (Optional[List[str]]): List of loaders to filter versions.
    - game_versions (Optional[List[str]]): List of game versions to filter versions.

    Returns:
    - List[Dict[str, Any]]: A list of versions for the specified project from the Modrinth API.
    """
    url = f"https://api.modrinth.com/v2/project/{project_id}/version"
    params = {"loaders": loaders, "game_versions": game_versions}

    # Filter out None values
    params = {k: v for k, v in params.items() if v is not None}

    response = request_get(url, params=params)
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


def prepare_categories(categories: List[str]) -> List[str]:
    return [
        category.lower()
        for category in categories
        if category not in blacklisted_categories
    ]


def get_modrinth_mods(db: dict = None):
    index = 0
    while True:
        results = modrinth_search(
            limit=PAGE_SIZE,
            offset=index,
            facets=[["project_type:mod"]],
            index="downloads",
        )["hits"]
        index += PAGE_SIZE

        for result in results:
            if db is not None and result["project_id"] in db:
                continue

            mod = Mod(
                result["project_id"],
                result["downloads"],
                prepare_categories(result["categories"]),
                result["license"],
                result["date_created"],
                "modrinth",
            )

            # Fetch versions
            for version in get_project_versions(result["project_id"]):
                for game_version in version["game_versions"]:
                    for loader in version["loaders"]:
                        mod.versions.append(
                            Version(
                                version["id"],
                                game_version,
                                loader.lower(),
                                version["downloads"],
                                version["date_published"],
                            )
                        )

            mod.post_process()

            yield mod
