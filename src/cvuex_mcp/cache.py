"""In-memory cache for Moodle answers, so repeated questions don't repeat requests."""

import time
from collections.abc import Awaitable, Callable, Hashable
from typing import Any


class TTLCache:
    """Remembers each value for a given number of seconds. Failures are never cached.

    It lives as long as the server process and only stores the few distinct
    requests the tools make, so it has no size limit.
    """

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._entries: dict[Hashable, tuple[float, Any]] = {}

    async def get_or_load(
        self, key: Hashable, ttl: float, load: Callable[[], Awaitable[Any]]
    ) -> Any:
        if ttl <= 0:
            return await load()

        entry = self._entries.get(key)
        if entry is not None and entry[0] > self._clock():
            return entry[1]

        value = await load()
        self._entries[key] = (self._clock() + ttl, value)
        return value

    def clear(self) -> None:
        self._entries.clear()
