"""Where the server keeps its files, and how it writes them.

The server's own files live in the user's configuration directory
(``platformdirs`` picks the right one for each operating system), which can
be overridden with the ``CVUEX_MCP_HOME`` environment variable.

Downloaded course materials go to a visible folder instead, so the student
can open them too: ``Documents/CVUEx`` or ``CVUEX_MCP_MATERIALES``.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from platformdirs import user_config_path, user_documents_path

APP_NAME = "cvuex-mcp"
HOME_ENV_VAR = "CVUEX_MCP_HOME"
MATERIALS_ENV_VAR = "CVUEX_MCP_MATERIALES"
MATERIALS_FOLDER = "CVUEx"


def app_dir() -> Path:
    base = os.environ.get(HOME_ENV_VAR)
    return Path(base) if base else user_config_path(APP_NAME, appauthor=False)


def materials_dir() -> Path:
    base = os.environ.get(MATERIALS_ENV_VAR)
    return Path(base) if base else user_documents_path() / MATERIALS_FOLDER


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def write_json(path: Path, data: dict[str, Any]) -> None:
    write_file(path, json.dumps(data, indent=2).encode("utf-8"))


def write_file(path: Path, content: bytes) -> None:
    """Write atomically, so a crash never leaves a half-written file.

    ``mkstemp`` creates the file readable only by its owner (0600 on
    POSIX); on Windows the per-user folders are already private.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}-")
    try:
        with os.fdopen(fd, "wb") as tmp:
            tmp.write(content)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
