"""Bring the forum index up to date with the campus.

Incremental: only discussions that changed since they were indexed are read
again, and those without replies need no request of their own (their message
comes in the list of discussions). Reading the replies uses
``mod_forum_get_discussion_posts``, which marks them as read if the student
tracks the forum's unread posts.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cvuex_mcp.campus.core import Campus
from cvuex_mcp.campus.forums import LAST_POST_FIRST, course_forums
from cvuex_mcp.formatting import discussion_url, html_to_text
from cvuex_mcp.forum_search.index import Discussion, ForumIndex, Post
from cvuex_mcp.jobs import JobProgress
from cvuex_mcp.models import Asignatura
from cvuex_mcp.moodle import InvalidTokenError, MoodleError

PER_PAGE = 100
FRESH_FOR_SECONDS = 10 * 60
"""An index refreshed less than this long ago is used as it is."""


@dataclass
class ForumProgress(JobProgress):
    courses: list[str] = field(default_factory=list)
    discussions: int = 0
    """Found in the campus so far."""
    checked: int = 0
    updated: int = 0
    removed: int = 0
    warnings: list[str] = field(default_factory=list)


def is_stale(index: ForumIndex, course_id: int, now: float) -> bool:
    refreshed = index.refreshed_at(course_id)
    return refreshed is None or now - refreshed > FRESH_FOR_SECONDS


async def refresh_forums(
    campus: Campus,
    courses: list[Asignatura],
    progress: ForumProgress,
    *,
    index_path: Path | None = None,
) -> None:
    progress.courses = [course.nombre for course in courses]
    index = ForumIndex(index_path)
    try:
        for course in courses:
            await _refresh_course(campus, index, course, progress)
    finally:
        index.close()


async def _refresh_course(
    campus: Campus, index: ForumIndex, course: Asignatura, progress: ForumProgress
) -> None:
    in_campus: set[int] = set()
    try:
        forums = await course_forums(campus, [course.id])
    except InvalidTokenError:
        raise
    except MoodleError as error:
        progress.warnings.append(f"No se pudieron consultar los foros de {course.nombre}: {error}")
        return
    complete = True
    for forum in forums:
        try:
            discussions = await _discussions(campus, forum["id"])
        except InvalidTokenError:
            raise
        except MoodleError as error:
            progress.warnings.append(f"No se pudo consultar el foro {forum['name']}: {error}")
            complete = False
            continue
        progress.discussions += len(discussions)
        for discussion in discussions:
            in_campus.add(discussion["discussion"])
            if index.timemodified(discussion["discussion"]) != discussion["timemodified"]:
                try:
                    posts = await _posts(campus, discussion)
                except InvalidTokenError:
                    raise
                except MoodleError as error:
                    progress.warnings.append(f"No se pudo leer «{discussion['name']}»: {error}")
                    complete = False
                else:
                    index.store(_discussion(campus, course, forum, discussion), posts)
                    progress.updated += 1
            progress.checked += 1
    if complete:  # otherwise an unreadable forum would look like deleted discussions
        progress.removed += index.forget_others(course.id, in_campus)
    index.mark_refreshed(course.id)


async def _discussions(campus: Campus, forum_id: int) -> list[dict[str, Any]]:
    """Every discussion of the forum, page by page."""
    discussions: list[dict[str, Any]] = []
    page = 0
    while True:
        answer = await campus.call(
            "mod_forum_get_forum_discussions",
            fresh=True,
            forumid=forum_id,
            sortorder=LAST_POST_FIRST,
            page=page,
            perpage=PER_PAGE,
        )
        discussions += answer["discussions"]
        if len(answer["discussions"]) < PER_PAGE:
            return discussions
        page += 1


async def _posts(campus: Campus, discussion: dict[str, Any]) -> list[Post]:
    if not discussion["numreplies"]:  # the list already has its only message
        return [
            Post(
                subject=discussion["subject"] or discussion["name"],
                message=html_to_text(discussion["message"]),
                author=discussion.get("userfullname"),
                created=max(discussion["created"], discussion.get("timestart") or 0),
            )
        ]
    answer = await campus.call(
        "mod_forum_get_discussion_posts",
        fresh=True,
        discussionid=discussion["discussion"],
        sortby="created",
        sortdirection="ASC",
    )
    return [
        Post(
            subject=post["subject"],
            message=html_to_text(post["message"]),
            author=(post.get("author") or {}).get("fullname"),
            created=post.get("timecreated") or 0,
        )
        for post in answer["posts"]
    ]


def _discussion(
    campus: Campus, course: Asignatura, forum: dict[str, Any], discussion: dict[str, Any]
) -> Discussion:
    return Discussion(
        id=discussion["discussion"],
        course_id=course.id,
        course=course.nombre,
        forum=forum["name"],
        title=discussion["name"],
        replies=discussion["numreplies"],
        timemodified=discussion["timemodified"],
        url=discussion_url(campus.site, discussion["discussion"]),
    )
