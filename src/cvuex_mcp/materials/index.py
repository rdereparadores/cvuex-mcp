"""Full-text search over the downloaded materials, with SQLite FTS5.

It lives in the same database as the manifest. Searching needs no request to
the campus: it only reads what has already been downloaded.
"""

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from cvuex_mcp.fulltext import TOKENIZER, all_or_any, search_words
from cvuex_mcp.materials.extract import Extraction
from cvuex_mcp.materials.manifest import MANIFEST_FILENAME
from cvuex_mcp.storage import app_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,  -- relative to the materials folder, as in the manifest
    course_id INTEGER NOT NULL,
    course TEXT NOT NULL,
    section TEXT NOT NULL,
    module TEXT NOT NULL,
    module_url TEXT,
    stamp TEXT NOT NULL,        -- size and modification time of the indexed file
    status TEXT NOT NULL,
    unit TEXT NOT NULL,
    parts INTEGER NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(
    text,
    heading,
    document_id UNINDEXED,
    number UNINDEXED,
    tokenize = '{TOKENIZER}'
);
"""


@dataclass(frozen=True)
class DocumentInfo:
    """Where a document comes from, from the manifest."""

    path: str
    course_id: int
    course: str
    section: str
    module: str
    module_url: str | None
    stamp: str


@dataclass(frozen=True)
class Document(DocumentInfo):
    id: int
    status: str
    unit: str
    parts: int


@dataclass(frozen=True)
class Match:
    document: Document
    number: int
    heading: str | None
    snippet: str


class MaterialsIndex:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or app_dir() / MANIFEST_FILENAME
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path)
        self._db.execute("PRAGMA journal_mode = WAL")  # searches while a sync writes
        self._db.executescript(SCHEMA.format(TOKENIZER=TOKENIZER))

    def close(self) -> None:
        self._db.close()

    def is_current(self, path: str, stamp: str) -> bool:
        row = self._db.execute("SELECT stamp FROM documents WHERE path = ?", (path,)).fetchone()
        return row is not None and row[0] == stamp

    def store(self, info: DocumentInfo, extraction: Extraction) -> None:
        """Index (or re-index) a document. Its id stays the same."""
        with self._db:
            (document_id,) = self._db.execute(
                """
                INSERT INTO documents (
                    path, course_id, course, section, module, module_url,
                    stamp, status, unit, parts
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (path) DO UPDATE SET
                    course_id = excluded.course_id, course = excluded.course,
                    section = excluded.section, module = excluded.module,
                    module_url = excluded.module_url, stamp = excluded.stamp,
                    status = excluded.status, unit = excluded.unit, parts = excluded.parts
                RETURNING id
                """,
                (
                    info.path,
                    info.course_id,
                    info.course,
                    info.section,
                    info.module,
                    info.module_url,
                    info.stamp,
                    extraction.status,
                    extraction.unit,
                    len(extraction.parts),
                ),
            ).fetchone()
            self._db.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
            self._db.executemany(
                "INSERT INTO chunks (text, heading, document_id, number) VALUES (?, ?, ?, ?)",
                [(p.text, p.heading or "", document_id, p.number) for p in extraction.parts],
            )

    def document(self, document_id: int) -> Document | None:
        row = self._db.execute(
            f"SELECT {DOCUMENT_COLUMNS} FROM documents WHERE id = ?", (document_id,)
        ).fetchone()
        return Document(*row) if row else None

    def documents(self, status: str | None = None) -> list[Document]:
        query = f"SELECT {DOCUMENT_COLUMNS} FROM documents"
        rows = self._db.execute(
            f"{query} WHERE status = ? ORDER BY path" if status else f"{query} ORDER BY path",
            (status,) if status else (),
        )
        return [Document(*row) for row in rows]

    def parts(self, document_id: int, first: int, last: int) -> list[tuple[int, str | None, str]]:
        """Number, heading and text of the document's parts in ``[first, last]``."""
        rows = self._db.execute(
            """
            SELECT number, heading, text FROM chunks
            WHERE document_id = ? AND number BETWEEN ? AND ?
            ORDER BY CAST(number AS INTEGER), rowid
            """,
            (document_id, first, last),
        )
        return [(int(number), heading or None, text) for number, heading, text in rows]

    def last_number(self, document_id: int) -> int:
        """The last page, slide or section with text."""
        (last,) = self._db.execute(
            "SELECT max(CAST(number AS INTEGER)) FROM chunks WHERE document_id = ?", (document_id,)
        ).fetchone()
        return last or 0

    def search(
        self, query: str, *, course_id: int | None = None, limit: int = 10
    ) -> tuple[list[Match], bool]:
        """Best matches, and whether they contain every word (else any of them)."""
        words = search_words(query)
        if not words:
            return [], True
        for fts_query, all_words in all_or_any(words):
            matches = self._search(fts_query, course_id, limit)
            if matches:
                return matches, all_words
        return [], len(words) <= 1

    def _search(self, fts_query: str, course_id: int | None, limit: int) -> list[Match]:
        course_filter = "AND d.course_id = ?" if course_id is not None else ""
        rows = self._db.execute(
            f"""
            SELECT {prefixed("d", DOCUMENT_COLUMNS)}, c.number, c.heading,
                   snippet(chunks, 0, '«', '»', '…', 30)
            FROM chunks c JOIN documents d ON d.id = c.document_id
            WHERE chunks MATCH ? {course_filter}
            ORDER BY bm25(chunks, 1.0, 2.0)
            LIMIT ?
            """,
            (fts_query, *((course_id,) if course_id is not None else ()), limit),
        )
        columns = len(DOCUMENT_COLUMNS.split(","))
        return [
            Match(Document(*row[:columns]), int(row[columns]), row[columns + 1] or None, row[-1])
            for row in rows
        ]


DOCUMENT_COLUMNS = (
    "path, course_id, course, section, module, module_url, stamp, id, status, unit, parts"
)


def prefixed(alias: str, columns: str) -> str:
    return ", ".join(f"{alias}.{column.strip()}" for column in columns.split(","))
