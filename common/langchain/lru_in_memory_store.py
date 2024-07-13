from cachetools import LRUCache
from langchain_core.stores import InMemoryStore


class LRUInMemoryStore(InMemoryStore):
    def __init__(self, maxsize: int) -> None:
        super().__init__()

        self.store = LRUCache(maxsize=maxsize)
