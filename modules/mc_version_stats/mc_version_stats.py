import time
from threading import Thread

from a2wsgi import WSGIMiddleware

from main import Configurator
from modules.mc_version_stats.curseforge import get_cf_mods
from modules.mc_version_stats.dashboard import get_app
from modules.mc_version_stats.data import get_db
from modules.mc_version_stats.modrinth import get_modrinth_mods


def to_metrics(counts: dict[str, int]):
    return "\n".join(
        [
            f'ff_votes_count{{handler="{name}"}} {value}'
            for name, value in counts.items()
        ]
    )


def init(configurator: Configurator):
    configurator.register(
        "Minecraft Version Stats", "Metrics endpoint for analysing version popularity."
    )

    def updater(sleep_time: int = 4):
        first_run = True
        while True:
            for provider in [get_modrinth_mods]:  # get_cf_mods
                db = get_db()
                mods = provider(db if first_run else None)
                try:
                    for mod in mods:
                        db[mod.id] = mod
                        db.sync()
                        time.sleep(sleep_time * (1 if first_run else 5))
                except Exception as e:
                    print(f"Failed to update {provider.__name__}: {e}")
            first_run = False

    Thread(target=updater, daemon=False).start()

    # noinspection PyTypeChecker
    configurator.app.mount("/dashboard", WSGIMiddleware(get_app("/dashboard/").server))
