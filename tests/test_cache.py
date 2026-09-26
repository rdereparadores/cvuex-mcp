import pytest

from cvuex_mcp.cache import TTLCache


class Counter:
    def __init__(self) -> None:
        self.loads = 0

    async def load(self) -> int:
        self.loads += 1
        return self.loads


@pytest.fixture
def clock():
    class Clock:
        now = 0.0

        def __call__(self) -> float:
            return self.now

    return Clock()


async def test_reuses_value_until_it_expires(clock):
    cache, counter = TTLCache(clock=clock), Counter()
    assert await cache.get_or_load("k", 10, counter.load) == 1
    clock.now = 9
    assert await cache.get_or_load("k", 10, counter.load) == 1
    clock.now = 10
    assert await cache.get_or_load("k", 10, counter.load) == 2


async def test_keys_are_independent(clock):
    cache, counter = TTLCache(clock=clock), Counter()
    assert await cache.get_or_load("a", 10, counter.load) == 1
    assert await cache.get_or_load("b", 10, counter.load) == 2


async def test_zero_ttl_never_caches(clock):
    cache, counter = TTLCache(clock=clock), Counter()
    await cache.get_or_load("k", 0, counter.load)
    await cache.get_or_load("k", 0, counter.load)
    assert counter.loads == 2


async def test_failures_are_not_cached(clock):
    cache, counter = TTLCache(clock=clock), Counter()

    async def failing():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await cache.get_or_load("k", 10, failing)
    assert await cache.get_or_load("k", 10, counter.load) == 1


async def test_clear_forgets_everything(clock):
    cache, counter = TTLCache(clock=clock), Counter()
    await cache.get_or_load("k", 10, counter.load)
    cache.clear()
    assert await cache.get_or_load("k", 10, counter.load) == 2


async def test_fresh_loads_again_and_caches_the_new_value():
    cache, counter = TTLCache(clock=lambda: 0), Counter()
    assert await cache.get_or_load("k", 60, counter.load) == 1
    assert await cache.get_or_load("k", 60, counter.load, fresh=True) == 2
    assert await cache.get_or_load("k", 60, counter.load) == 2
