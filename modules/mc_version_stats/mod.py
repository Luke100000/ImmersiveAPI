from dataclasses import dataclass, field

from modules.mc_version_stats.utils import age_in_days


def get_adjusted_estimate(
    downloads: int, age: int, time_span: int, update_rate: float = 365
):
    age_fraction = age / time_span
    rate = downloads / age
    final_rate = rate * update_rate / (update_rate + time_span)
    return int(
        rate * time_span * age_fraction + final_rate * time_span * (1 - age_fraction)
    )


@dataclass
class Version:
    id: str
    game_version: str
    mod_loader: str
    downloads: int
    date: str
    newest: bool = False

    @property
    def age(self):
        return age_in_days(self.date)

    def get_discounted_downloads(
        self, time_span: int, extrapolate: bool = False, interpolate: bool = False
    ):
        if self.age > time_span:
            if self.newest and interpolate:
                # Outside the time span, but the newest version, so It's still being downloaded
                # We estimate downloads with a uniform distribution
                return int(self.downloads / self.age * time_span)
            else:
                # Outside the time span and not the newest version, so we assume no downloads
                return 0
        else:
            if self.newest and extrapolate:
                # Inside the time span, and the newest one, so we extrapolate to the full time span
                return get_adjusted_estimate(self.downloads, self.age, time_span)
            else:
                # Inside the time span, so we return the full download count
                return self.downloads


@dataclass
class Mod:
    id: str
    downloads: int
    categories: list[str]
    license: str
    date: str
    website: str
    versions: list[Version] = field(default_factory=list)

    @property
    def age(self):
        return age_in_days(self.date)

    def post_process(self):
        self.versions = sorted(self.versions, key=lambda v: v.age)
        updates = set()
        for version in self.versions:
            index = (version.mod_loader, version.game_version)
            version.newest = index not in updates
            updates.add(index)
