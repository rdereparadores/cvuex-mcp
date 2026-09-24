"""Storage of the Moodle tokens obtained at login.

Tokens live in a JSON file in the user's configuration directory
(``platformdirs`` picks the right one for each operating system), with one
entry per platform::

    {"avuex": {"token": "...", "private_token": "..."}}

The directory can be overridden with the ``CVUEX_MCP_HOME`` environment variable.
"""

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from platformdirs import user_config_path

APP_NAME = "cvuex-mcp"
HOME_ENV_VAR = "CVUEX_MCP_HOME"
CREDENTIALS_FILENAME = "credentials.json"


@dataclass(frozen=True)
class Credentials:
    token: str
    """Web service token. It grants the same access as the student's account."""

    private_token: str | None = None
    """Only issued right after a fresh login; Moodle uses it to open
    authenticated web pages (autologin). It cannot be retrieved later."""


def default_credentials_path() -> Path:
    base = os.environ.get(HOME_ENV_VAR)
    directory = Path(base) if base else user_config_path(APP_NAME, appauthor=False)
    return directory / CREDENTIALS_FILENAME


class CredentialStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_credentials_path()

    def load(self, site_key: str) -> Credentials | None:
        entry = self._read_all().get(site_key)
        return Credentials(**entry) if entry else None

    def save(self, site_key: str, credentials: Credentials) -> None:
        entries = self._read_all()
        entries[site_key] = asdict(credentials)
        self._write_all(entries)

    def delete(self, site_key: str) -> bool:
        """Remove a platform's credentials. Returns whether there were any."""
        entries = self._read_all()
        if entries.pop(site_key, None) is None:
            return False
        self._write_all(entries)
        return True

    def _read_all(self) -> dict[str, dict]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}

    def _write_all(self, entries: dict[str, dict]) -> None:
        """Write atomically so a crash never leaves a half-written file.

        ``mkstemp`` creates the file readable only by its owner (0600 on
        POSIX); on Windows the per-user config directory is already private.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=self.path.parent, prefix=".credentials-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp:
                json.dump(entries, tmp, indent=2)
            os.replace(tmp_name, self.path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
