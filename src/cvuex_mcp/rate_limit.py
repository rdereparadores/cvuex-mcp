"""Keeps the load on the campus servers low."""

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

DEFAULT_MIN_INTERVAL_SECONDS = 0.3


class RateLimiter:
    """Allows one request at a time, with a minimum gap between consecutive ones."""

    def __init__(
        self,
        min_interval: float = DEFAULT_MIN_INTERVAL_SECONDS,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._lock = asyncio.Lock()
        self._last_finished = float("-inf")

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        async with self._lock:
            wait = self._last_finished + self.min_interval - self._clock()
            if wait > 0:
                await self._sleep(wait)
            try:
                yield
            finally:
                self._last_finished = self._clock()
