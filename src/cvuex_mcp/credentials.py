"""Storage of the Moodle tokens obtained at login.

Tokens live in ``credentials.json`` in the app directory (see ``storage``),
with one entry per platform::

    {"avuex": {"token": "...", "private_token": "..."}}
"""

from dataclasses import asdict, dataclass
from pathlib import Path

from cvuex_mcp.storage import app_dir, read_json, write_json

CREDENTIALS_FILENAME = "credentials.json"


@dataclass(frozen=True)
class Credentials:
    token: str
    """Web service token. It grants the same access as the student's account."""

    private_token: str | None = None
    """Only issued right after a fresh login; Moodle uses it to open
    authenticated web pages (autologin). It cannot be retrieved later."""


def default_credentials_path() -> Path:
    return app_dir() / CREDENTIALS_FILENAME


class CredentialStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_credentials_path()

    def load(self, site_key: str) -> Credentials | None:
        entry = read_json(self.path).get(site_key)
        return Credentials(**entry) if entry else None

    def save(self, site_key: str, credentials: Credentials) -> None:
        entries = read_json(self.path)
        entries[site_key] = asdict(credentials)
        write_json(self.path, entries)

    def delete(self, site_key: str) -> bool:
        """Remove a platform's credentials. Returns whether there were any."""
        entries = read_json(self.path)
        if entries.pop(site_key, None) is None:
            return False
        write_json(self.path, entries)
        return True
