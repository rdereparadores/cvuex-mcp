"""Small values the server remembers between runs, kept in ``state.json``."""

from pathlib import Path
from typing import Any

from cvuex_mcp.storage import app_dir, read_json, write_json

STATE_FILENAME = "state.json"


class PersistentState:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or app_dir() / STATE_FILENAME

    def get(self, key: str) -> Any:
        return read_json(self.path).get(key)

    def set(self, key: str, value: Any) -> None:
        values = read_json(self.path)
        values[key] = value
        write_json(self.path, values)
