import time
from collections import defaultdict
from threading import Thread

from fastapi import Request
from fastapi.templating import Jinja2Templates

from main import Configurator
from modules.mc_version_stats.data import database
from modules.mc_version_stats.modrinth import (
    get_modrinth_mods,
    populate_modrinth_details,
)
from modules.mc_version_stats.utils import parse_versions, is_clean_version

DEBUG = True


def init(configurator: Configurator):
    configurator.register(
        "Minecraft Version Stats", "Metrics endpoint for analysing version popularity."
    )

    def updater():
        while not DEBUG:
            for mod in get_modrinth_mods("mod"):
                existing_mod = database.get_mod(mod.id)

                if existing_mod:
                    if existing_mod.last_modified != mod.last_modified:
                        populate_modrinth_details(mod)
                        database.add_mod(mod)
                        time.sleep(3)
                    else:
                        database.update_mod(mod)
                        time.sleep(0.1)
                else:
                    populate_modrinth_details(mod)
                    database.add_mod(mod)
                    time.sleep(3)
            time.sleep(60)

    Thread(target=updater, daemon=True).start()

    templates = Jinja2Templates(directory="modules/mc_version_stats/templates")

    def get_super_version(version: str) -> str:
        return ".".join(version.split(".")[:2])

    @configurator.get("/mcv/dashboard")
    def get_dashboard(request: Request):
        mods = database.get_mods()

        mods = [m for m in mods if "library" not in m.categories]

        versions = set()
        coverage = defaultdict(int)

        for mod in mods:
            for version in mod.versions:
                versions.add(version)
                coverage[version] += 1

        versions = [
            v
            for v in parse_versions(list(versions))
            if is_clean_version(v) and coverage[v] > 10
        ][::-1]
        coverage = {k: v for k, v in coverage.items() if k in versions}

        super_versions = set()
        super_version_max_coverage = defaultdict(int)
        versions_per_super_version = {}
        for version in versions:
            super_version = get_super_version(version)
            super_versions.add(super_version)

            super_version_max_coverage[super_version] = max(
                super_version_max_coverage[super_version], coverage[version]
            )
            versions_per_super_version.setdefault(super_version, []).append(version)

        super_versions = parse_versions(list(super_versions))
        global_max_coverage = max(super_version_max_coverage.values())

        context = {
            "total": len(mods),
            "versions": versions,
            "versions_per_super_version": versions_per_super_version,
            "preferred_versions": [
                v
                for v in versions
                if coverage[v] == super_version_max_coverage[get_super_version(v)]
            ],
            "super_versions": super_versions,
            "coverage": coverage,
            "relative_coverage": {
                k: v / super_version_max_coverage[get_super_version(k)]
                for k, v in coverage.items()
                if k in versions
            },
            "super_version_relative_coverage": {
                k: v / global_max_coverage
                for k, v in super_version_max_coverage.items()
            },
        }

        return templates.TemplateResponse(
            request=request, name="dashboard.jinja", context=context
        )

    return [get_dashboard]
