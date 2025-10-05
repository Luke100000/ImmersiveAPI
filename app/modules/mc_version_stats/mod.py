from dataclasses import dataclass, field

from .utils import age_in_days


@dataclass
class Mod:
    id: str
    source: str
    slug: str
    last_modified: int
    created_at: int

    name: str
    author: str
    description: str
    type: str
    categories: set[str]

    downloads: int
    follows: int

    body: str
    license: str
    links: dict[str, str]
    icon: str
    gallery: list[str]

    mod_loaders: set[str] = field(default_factory=set)
    versions: list[str] = field(default_factory=list)

    _age: int = -1

    @property
    def age(self):
        if self._age == -1:
            self._age = age_in_days(self.created_at)
        return self._age
