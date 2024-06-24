import json
import os
from functools import cache
from typing import Dict, Any, Optional, List

from dotenv import load_dotenv

from modules.mc_version_stats.mod import Mod, Version
from modules.mc_version_stats.utils import request_get

load_dotenv()

headers = {"Accept": "application/json", "x-api-key": os.getenv("CURSEFORGE_API_KEY")}

MINECRAFT_GAME_ID = 432
MINECRAFT_MOD_CLASS_ID = 6
PAGE_SIZE = 100


@cache
def get_categories():
    try:
        r = request_get(
            "https://api.curseforge.com/v1/categories",
            params={"gameId": MINECRAFT_GAME_ID},
            headers={"Accept": "application/json", "x-api-key": "API_KEY"},
        )
        r.raise_for_status()
        return [
            c["id"]
            for c in r.json()["data"]
            if "parentCategoryId" in c
            and c["parentCategoryId"] == MINECRAFT_MOD_CLASS_ID
        ]
    except Exception as e:
        print(e)
        with open("modules/mca_version_stats/categories.json") as f:
            return json.load(f)


def curseforge_search_mods(
    game_id: int = MINECRAFT_GAME_ID,
    search_filter: Optional[str] = None,
    class_id: Optional[int] = MINECRAFT_MOD_CLASS_ID,
    category_id: Optional[int] = None,
    category_ids: Optional[List[int]] = None,
    game_version: Optional[str] = None,
    index: Optional[int] = None,
    page_size: Optional[int] = None,
    sort_field: Optional[str] = None,
    sort_order: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Searches for mods on CurseForge.

    Parameters:
    - gameId (int): The ID of the game.
    - searchFilter (Optional[str]): The search filter string.
    - classId (Optional[int]): The class ID to filter by.
    - categoryId (Optional[int]): The category ID to filter by.
    - categoryIds (Optional[List[int]]): The category IDs to filter by.
    - gameVersion (Optional[str]): The game version to filter by.
    - index (Optional[int]): The number of results to skip.
    - pageSize (Optional[int]): The number of results to return.
    - sortField (Optional[int]): The field to sort by.
    - sortOrder (Optional[str]): The sort order ('asc' or 'desc').

    Returns:
    - Dict[str, Any]: The search results from the CurseForge API.
    """
    url = "https://api.curseforge.com/v1/mods/search"
    params = {
        "gameId": game_id,
        "searchFilter": search_filter,
        "classId": class_id,
        "categoryId": category_id,
        "categoryIds": category_ids,
        "gameVersion": game_version,
        "index": index,
        "pageSize": page_size,
        "sortField": sort_field,
        "sortOrder": sort_order,
    }

    # Filter out None values
    params = {k: v for k, v in params.items() if v is not None}

    response = request_get(url, headers=headers, params=params)
    response.raise_for_status()
    return response.json()


def get_mod_files(
    mod_id: int,
    game_version: Optional[str] = None,
    mod_loader_type: Optional[int] = None,
    index: Optional[int] = None,
    page_size: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Retrieves the files for a specific mod on CurseForge.

    Parameters:
    - modId (int): The ID of the mod.
    - gameVersion (Optional[str]): The game version to filter files by.
    - modLoaderType (Optional[int]): The mod loader type to filter files by.
    - index (Optional[int]): The number of results to skip.
    - pageSize (Optional[int]): The number of results to return.

    Returns:
    - Dict[str, Any]: The files for the specified mod from the CurseForge API.
    """
    url = f"https://api.curseforge.com/v1/mods/{mod_id}/files"
    params = {
        "gameVersion": game_version,
        "modLoaderType": mod_loader_type,
        "index": index,
        "pageSize": page_size,
    }

    # Filter out None values
    params = {k: v for k, v in params.items() if v is not None}

    response = request_get(url, headers=headers, params=params)
    response.raise_for_status()
    return response.json()


def get_all_mod_files(mod_id: int) -> List[Dict]:
    """
    Retrieves all files for a specific mod on CurseForge.
    """
    all_files = []
    index = 0
    while index + PAGE_SIZE < 10000:
        files = get_mod_files(mod_id, page_size=PAGE_SIZE, index=index)["data"]
        all_files.extend(files)
        if len(files) < PAGE_SIZE:
            break
        index += PAGE_SIZE
    return all_files


mod_loaders = {"Any", "Forge", "Cauldron", "LiteLoader", "Fabric", "Quilt", "NeoForge"}
sides = {"Client", "Server"}


def get_versions(versions: List[str]):
    game_versions = []
    loaders = []
    for version in versions:
        if version in mod_loaders:
            loaders.append(version)
        elif version in sides:
            continue
        else:
            game_versions.append(version)
    return game_versions, loaders


def get_cf_mods(db: dict = None):
    duplicates = set()
    for category_1 in get_categories():
        for category_2 in get_categories():
            if category_1 == category_2:
                continue
            index = 0
            while index + PAGE_SIZE < 10000:
                results = curseforge_search_mods(
                    game_id=MINECRAFT_GAME_ID,
                    index=index,
                    page_size=PAGE_SIZE,
                    sort_field="TotalDownloads",
                    sort_order="desc",
                    # We filter for 2 categories to bypass the 10k limit
                    category_ids=[
                        category_1,
                        category_2,
                    ],
                )["data"]
                index += PAGE_SIZE

                for result in results:
                    if db is not None and result["project_id"] in db:
                        continue

                    if result["id"] not in duplicates:
                        duplicates.add(result["id"])

                        mod = Mod(
                            str(result["id"]),
                            result["downloadCount"],
                            [c["name"].lower() for c in result["categories"]],
                            "unknown",
                            result["dateReleased"],
                            "curseforge",
                        )

                        # Fetch versions
                        for version in get_all_mod_files(result["id"]):
                            game_versions, loaders = get_versions(
                                version["gameVersions"]
                            )
                            for game_version in game_versions:
                                for loader in loaders:
                                    mod.versions.append(
                                        Version(
                                            str(version["id"]),
                                            game_version,
                                            loader.lower(),
                                            version["downloadCount"],
                                            version["fileDate"],
                                        )
                                    )

                        mod.post_process()

                        yield mod
