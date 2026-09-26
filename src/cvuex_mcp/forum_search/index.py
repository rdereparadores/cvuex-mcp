"""The local index of the forums: discussions and their posts, in SQLite FTS5."""

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from cvuex_mcp.fulltext import TOKENIZER, all_or_any, search_words
from cvuex_mcp.storage import app_dir

INDEX_FILENAME = "foros.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS discussions (
    id INTEGER PRIMARY KEY,     -- Moodle's discussion id
    course_id INTEGER NOT NULL,
    course TEXT NOT NULL,
    forum TEXT NOT NULL,
    title TEXT NOT NULL,
    replies INTEGER NOT NULL,
    timemodified INTEGER NOT NULL,
    url TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS posts USING fts5(
    subject,
    message,
    author UNINDEXED,
    created UNINDEXED,
    discussion_id UNINDEXED,
    tokenize = '{TOKENIZER}'
);
CREATE TABLE IF NOT EXISTS courses (
    course_id INTEGER PRIMARY KEY,
    refreshed_at REAL NOT NULL
);
"""


@dataclass(frozen=True)
class Discussion:
    id: int
    course_id: int
    course: str
    forum: str
    title: str
    replies: int
    timemodified: int
    url: str


@dataclass(frozen=True)
class Post:
    subject: str
    message: str
    author: str | None
    created: int


@dataclass(frozen=True)
class ForumMatch:
    discussion: Discussion
    author: str | None
    created: int
    snippet: str


DISCUSSION_COLUMNS = "id, course_id, course, forum, title, replies, timemodified, url"


class ForumIndex:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or app_dir() / INDEX_FILENAME
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path)
        self._db.execute("PRAGMA journal_mode = WAL")  # searches while the index is refreshed
        self._db.executescript(SCHEMA.format(TOKENIZER=TOKENIZER))

    def close(self) -> None:
        self._db.close()

    def timemodified(self, discussion_id: int) -> int | None:
        """When the discussion last changed, as indexed; None if it isn't."""
        row = self._db.execute(
            "SELECT timemodified FROM discussions WHERE id = ?", (discussion_id,)
        ).fetchone()
        return row[0] if row else None

    def store(self, discussion: Discussion, posts: list[Post]) -> None:
        """Index (or re-index) a discussion with all its posts."""
        with self._db:
            self._db.execute(
                f"INSERT OR REPLACE INTO discussions ({DISCUSSION_COLUMNS}) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    discussion.id,
                    discussion.course_id,
                    discussion.course,
                    discussion.forum,
                    discussion.title,
                    discussion.replies,
                    discussion.timemodified,
                    discussion.url,
                ),
            )
            self._db.execute("DELETE FROM posts WHERE discussion_id = ?", (discussion.id,))
            self._db.executemany(
                "INSERT INTO posts (subject, message, author, created, discussion_id) "
                "VALUES (?, ?, ?, ?, ?)",
                [(p.subject, p.message, p.author, p.created, discussion.id) for p in posts],
            )

    def forget_others(self, course_id: int, discussion_ids: set[int]) -> int:
        """Drop the course's discussions no longer in the campus; return how many."""
        indexed = self._db.execute(
            "SELECT id FROM discussions WHERE course_id = ?", (course_id,)
        ).fetchall()
        gone = [(id,) for (id,) in indexed if id not in discussion_ids]
        with self._db:
            self._db.executemany("DELETE FROM posts WHERE discussion_id = ?", gone)
            self._db.executemany("DELETE FROM discussions WHERE id = ?", gone)
        return len(gone)

    def mark_refreshed(self, course_id: int, when: float | None = None) -> None:
        with self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO courses VALUES (?, ?)", (course_id, when or time.time())
            )

    def refreshed_at(self, course_id: int) -> float | None:
        row = self._db.execute(
            "SELECT refreshed_at FROM courses WHERE course_id = ?", (course_id,)
        ).fetchone()
        return row[0] if row else None

    def count(self, course_id: int | None = None) -> int:
        query, params = "SELECT count(*) FROM discussions", ()
        if course_id is not None:
            query, params = f"{query} WHERE course_id = ?", (course_id,)
        return self._db.execute(query, params).fetchone()[0]

    def search(
        self, query: str, *, course_id: int | None = None, limit: int = 10
    ) -> tuple[list[ForumMatch], bool]:
        """The best post of each matching discussion, and whether they contain every word.

        The snippet always comes from the message: the title is given apart, and every
        reply repeats it in its subject ("Re: ...").
        """
        words = search_words(query)
        if not words:
            return [], True
        for fts_query, all_words in all_or_any(words):
            matches = self._search(fts_query, course_id, limit)
            if matches:
                return matches, all_words
        return [], len(words) <= 1

    def _search(self, fts_query: str, course_id: int | None, limit: int) -> list[ForumMatch]:
        course_filter = "AND d.course_id = ?" if course_id is not None else ""
        rows = self._db.execute(
            f"""
            SELECT {", ".join(f"d.{c.strip()}" for c in DISCUSSION_COLUMNS.split(","))},
                   p.author, p.created, snippet(posts, 1, '«', '»', '…', 30)
            FROM posts p JOIN discussions d ON d.id = p.discussion_id
            WHERE posts MATCH ? {course_filter}
            ORDER BY bm25(posts)
            """,
            (fts_query, *((course_id,) if course_id is not None else ())),
        )
        matches: dict[int, ForumMatch] = {}  # one per discussion: its best post
        for *discussion, author, created, snippet in rows:
            match = ForumMatch(Discussion(*discussion), author, int(created or 0), snippet)
            matches.setdefault(match.discussion.id, match)
            if len(matches) == limit:
                break
        return list(matches.values())
