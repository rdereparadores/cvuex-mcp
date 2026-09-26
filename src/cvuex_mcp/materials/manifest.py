"""What has been downloaded, kept in SQLite next to the server's other files.

The materials folder is the student's; this record says which of its files
came from the campus, so a sync never overwrites anything else.
"""

import sqlite3
from dataclasses import astuple, dataclass, fields
from pathlib import Path

from cvuex_mcp.storage import app_dir

MANIFEST_FILENAME = "materiales.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS courses (
    course_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    folder TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS files (
    course_id INTEGER NOT NULL,
    key TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE,  -- relative to the materials folder
    section TEXT NOT NULL,
    module TEXT NOT NULL,
    module_url TEXT,
    kind TEXT NOT NULL,
    size INTEGER NOT NULL,
    timemodified INTEGER NOT NULL,
    downloaded_at INTEGER NOT NULL,
    in_campus INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (course_id, key)
);
"""


@dataclass(frozen=True)
class Entry:
    course_id: int
    key: str
    path: str
    section: str
    module: str
    module_url: str | None
    kind: str
    size: int
    timemodified: int
    downloaded_at: int
    in_campus: bool = True
    """False once the teacher removes it from the campus; the local copy is kept."""


COLUMNS = ", ".join(field.name for field in fields(Entry))


class Manifest:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or app_dir() / MANIFEST_FILENAME
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path)
        self._db.executescript(SCHEMA)

    def close(self) -> None:
        self._db.close()

    def course_folder(self, course_id: int, name: str, wanted: str) -> str:
        """The course's folder: the one it already has, or ``wanted`` if free."""
        row = self._db.execute(
            "SELECT folder FROM courses WHERE course_id = ?", (course_id,)
        ).fetchone()
        if row:
            return row[0]
        taken = {folder.casefold() for (folder,) in self._db.execute("SELECT folder FROM courses")}
        folder = wanted if wanted.casefold() not in taken else f"{wanted} ({course_id})"
        with self._db:
            self._db.execute("INSERT INTO courses VALUES (?, ?, ?)", (course_id, name, folder))
        return folder

    def get(self, course_id: int, key: str) -> Entry | None:
        row = self._db.execute(
            f"SELECT {COLUMNS} FROM files WHERE course_id = ? AND key = ?", (course_id, key)
        ).fetchone()
        return _entry(row) if row else None

    def path_owner(self, path: str) -> tuple[int, str] | None:
        """Which campus file a local path belongs to (case-insensitively), if any."""
        row = self._db.execute(
            "SELECT course_id, key FROM files WHERE lower(path) = lower(?)", (path,)
        ).fetchone()
        return tuple(row) if row else None

    def save(self, entry: Entry) -> None:
        placeholders = ", ".join("?" * len(fields(Entry)))
        with self._db:
            self._db.execute(
                f"INSERT OR REPLACE INTO files ({COLUMNS}) VALUES ({placeholders})",
                astuple(entry),
            )

    def mark_removed(self, course_id: int, keys_in_campus: set[str]) -> int:
        """Flag the course's files that are no longer in the campus; return how many."""
        rows = self._db.execute(
            "SELECT key FROM files WHERE course_id = ? AND in_campus = 1", (course_id,)
        ).fetchall()
        gone = [key for (key,) in rows if key not in keys_in_campus]
        with self._db:
            self._db.executemany(
                "UPDATE files SET in_campus = 0 WHERE course_id = ? AND key = ?",
                [(course_id, key) for key in gone],
            )
        return len(gone)

    def files(self, course_id: int | None = None) -> list[Entry]:
        query, params = f"SELECT {COLUMNS} FROM files", ()
        if course_id is not None:
            query, params = f"{query} WHERE course_id = ?", (course_id,)
        return [_entry(row) for row in self._db.execute(f"{query} ORDER BY path", params)]


def _entry(row: tuple) -> Entry:
    *values, in_campus = row  # SQLite has no booleans
    return Entry(*values, in_campus=bool(in_campus))
