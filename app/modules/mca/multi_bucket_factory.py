from pyrate_limiter import (
    AbstractBucket,
    BucketFactory,
    InMemoryBucket,
    RateItem,
    TimeClock,
)


class MultiBucketFactory(BucketFactory):
    def __init__(self, rates):
        self.clock = TimeClock()
        self.rates = rates
        self.buckets = {}

    def wrap_item(self, name: str, weight: int = 1) -> RateItem:
        return RateItem(name, self.clock.now(), weight=weight)

    def get(self, item: RateItem) -> AbstractBucket:
        if item.name not in self.buckets:
            new_bucket = self.create(self.clock, InMemoryBucket, self.rates)
            self.buckets.update({item.name: new_bucket})

        return self.buckets[item.name]
