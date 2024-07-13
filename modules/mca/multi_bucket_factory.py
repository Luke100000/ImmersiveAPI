from multiprocessing.pool import ThreadPool

from pyrate_limiter import (
    BucketFactory,
    RateItem,
    AbstractBucket,
    InMemoryBucket,
    TimeClock,
)


class MultiBucketFactory(BucketFactory):
    def __init__(self, rates):
        self.clock = TimeClock()
        self.rates = rates
        self.buckets = {}
        self.thread_pool = ThreadPool(2)

    def wrap_item(self, name: str, weight: int = 1) -> RateItem:
        return RateItem(name, self.clock.now(), weight=weight)

    def get(self, item: RateItem) -> AbstractBucket:
        if item.name not in self.buckets:
            new_bucket = self.create(self.clock, InMemoryBucket, self.rates)
            self.buckets.update({item.name: new_bucket})

        return self.buckets[item.name]
