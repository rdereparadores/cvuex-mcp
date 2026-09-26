"""Only one sync at a time, even between the MCP server and the command line."""

import os
import time
from pathlib import Path
from typing import Self

from cvuex_mcp.storage import app_dir

LOCK_FILENAME = "sincronizacion.lock"
STALE_AFTER_SECONDS = 15 * 60
"""A sync refreshes its lock after every file; an older one was left by a crash."""


class SyncLockedError(Exception):
    def __init__(self) -> None:
        super().__init__(
            "Ya hay una sincronización de materiales en marcha (quizá desde la terminal). "
            "Espera a que termine."
        )


class SyncLock:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or app_dir() / LOCK_FILENAME

    def __enter__(self) -> Self:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self._is_stale():
            self.path.unlink(missing_ok=True)
        try:
            os.close(os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        except FileExistsError:
            raise SyncLockedError from None
        return self

    def __exit__(self, *_exc_info) -> None:
        self.path.unlink(missing_ok=True)

    def refresh(self) -> None:
        self.path.touch()

    def _is_stale(self) -> bool:
        try:
            return time.time() - self.path.stat().st_mtime > STALE_AFTER_SECONDS
        except FileNotFoundError:
            return False
