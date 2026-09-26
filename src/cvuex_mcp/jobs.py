"""Work that runs in the background, because it can take longer than the time
an MCP client waits for a tool call (opencode: 15 s). A tool starts it and
reports its progress; calling the tool again reports how it is going."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import httpx

from cvuex_mcp.moodle import InvalidTokenError, MoodleError
from cvuex_mcp.session import expired_session_message

logger = logging.getLogger(__name__)


@dataclass
class JobProgress:
    """Updated as the job goes, so it can be reported while it runs."""

    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    error: str | None = None
    """Why it stopped, for the student, if it stopped."""


class BackgroundJob[P: JobProgress]:
    """At most one run at a time; its progress can be read while it runs."""

    def __init__(self) -> None:
        self.progress: P | None = None
        self._task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(
        self,
        run: Callable[[P], Awaitable[None]],
        progress: P,
        *,
        expected: tuple[type[Exception], ...] = (),
    ) -> P:
        """Run ``run(progress)``. ``expected`` errors are reported as their message."""
        self.progress = progress
        self._task = asyncio.create_task(_run(run, progress, expected))
        return progress

    async def wait(self, seconds: float) -> None:
        """Wait for the job to end, at most ``seconds``."""
        if self._task:
            await asyncio.wait({self._task}, timeout=seconds)

    async def cancel(self) -> None:
        if self.running:
            self._task.cancel()
            await asyncio.wait({self._task})


async def _run[P: JobProgress](
    run: Callable[[P], Awaitable[None]], progress: P, expected: tuple[type[Exception], ...]
) -> None:
    """Nobody awaits a background task, so every failure is kept in ``progress``."""
    try:
        await run(progress)
    except InvalidTokenError:
        progress.error = expired_session_message()
    except (MoodleError, httpx.HTTPError, OSError, *expected) as error:
        progress.error = str(error)
    except Exception as error:
        logger.exception("Error inesperado en una tarea en segundo plano")
        progress.error = f"Error inesperado: {error}"
    finally:
        progress.finished_at = time.time()
