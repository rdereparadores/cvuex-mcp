import asyncio

from cvuex_mcp.rate_limit import RateLimiter


class FakeTime:
    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def limiter(fake: FakeTime, min_interval: float = 1.0) -> RateLimiter:
    return RateLimiter(min_interval, clock=fake.clock, sleep=fake.sleep)


async def test_first_request_does_not_wait():
    fake = FakeTime()
    async with limiter(fake).slot():
        pass
    assert fake.sleeps == []


async def test_waits_only_for_the_rest_of_the_interval():
    fake = FakeTime()
    rate_limiter = limiter(fake)
    async with rate_limiter.slot():
        pass
    fake.now += 0.25
    async with rate_limiter.slot():
        pass
    assert fake.sleeps == [0.75]


async def test_requests_never_overlap():
    rate_limiter = RateLimiter(min_interval=0)
    running = 0
    max_running = 0

    async def request():
        nonlocal running, max_running
        async with rate_limiter.slot():
            running += 1
            max_running = max(max_running, running)
            await asyncio.sleep(0.01)
            running -= 1

    await asyncio.gather(*(request() for _ in range(5)))
    assert max_running == 1
