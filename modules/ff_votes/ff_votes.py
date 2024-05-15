import requests
from bs4 import BeautifulSoup
from cachetools import cached, TTLCache
from starlette.responses import Response

from main import Configurator


def get_counts():
    html_doc = requests.request("get", "https://www.tips.at/sympathicus/wahl").content
    soup = BeautifulSoup(html_doc, "html.parser")

    counts = {}
    for entry in soup.find_all("tr"):
        entry = [v for v in entry.text.split("\n") if v]
        if len(entry) == 3:
            name = entry[0].split("(")[0].strip()
            count = int(entry[1].replace("\xa0", "").replace(".", ""))
            counts[name] = count
    return counts


def to_metrics(counts: dict[str, int]):
    return "\n".join(
        [
            f'ff_votes_count{{handler="{name}"}} {value}'
            for name, value in counts.items()
        ]
    )


@cached(TTLCache(1, 60))
def get_ff_votes_metrics():
    return to_metrics(get_counts())


def init(configurator: Configurator):
    configurator.register("Sympathicus 2024", "Metrics endpoint for Sympathicus 2024.")

    @configurator.get("/ff_votes/metrics")
    def get_fusion():
        return Response(get_ff_votes_metrics(), media_type="text/plain")
