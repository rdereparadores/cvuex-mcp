"""Announcements and discussions in the course forums."""

from typing import Any

from cvuex_mcp.campus.core import Campus
from cvuex_mcp.formatting import discussion_url, html_to_text, iso_datetime, short_text
from cvuex_mcp.models import Aviso, Debate, ListaAvisos, MensajeForo
from cvuex_mcp.moodle import InvalidTokenError, MoodleError

DAY_SECONDS = 24 * 60 * 60
# The teachers' announcements forum and the standard forum for everyone.
ANNOUNCEMENT_FORUM_TYPES = {"news", "general"}
LAST_POST_FIRST = 1  # Moodle's discussion sort order (pinned ones always come first)
MESSAGE_PREVIEW_CHARS = 500


class DiscussionNotFoundError(Exception):
    def __init__(self, discussion_id: int) -> None:
        super().__init__(
            f"No se pudo abrir el debate {discussion_id}: no existe o no tienes acceso. "
            "Usa un debate_id de los que da avisos."
        )


async def announcements(
    campus: Campus, days: int, limit: int, course_id: int | None = None
) -> ListaAvisos:
    """Discussions started or answered in the last ``days``, newest activity first.

    Reading them this way doesn't mark anything as read.
    """
    since = int(campus.now()) // 60 * 60 - days * DAY_SECONDS
    course_names = {c.id: c.nombre for c in await campus.courses("all")}
    if course_id is None:
        course_ids = [c.id for c in await campus.courses("inprogress")]
    else:
        course_ids = [course_id]

    found = []
    for forum in await _forums(campus, course_ids):
        if forum["type"] not in ANNOUNCEMENT_FORUM_TYPES:
            continue
        answer = await campus.call(
            "mod_forum_get_forum_discussions",
            forumid=forum["id"],
            sortorder=LAST_POST_FIRST,
            page=0,
            perpage=limit,
        )
        found += [
            (discussion["timemodified"], _announcement(campus, forum, discussion, course_names))
            for discussion in answer["discussions"]
            if discussion["timemodified"] >= since
        ]

    found.sort(key=lambda pair: pair[0], reverse=True)
    return ListaAvisos(
        desde=iso_datetime(since),
        avisos=[announcement for _, announcement in found[:limit]],
    )


async def read_discussion(campus: Campus, discussion_id: int) -> Debate:
    """Every post of a discussion, oldest first.

    Moodle marks them as read if the student tracks the forum's unread posts.
    """
    try:
        answer = await campus.call(
            "mod_forum_get_discussion_posts",
            discussionid=discussion_id,
            sortby="created",
            sortdirection="ASC",
        )
    except InvalidTokenError:
        raise
    except MoodleError as error:  # Moodle fails with a PHP error on unknown ids
        raise DiscussionNotFoundError(discussion_id) from error
    posts = answer["posts"]
    first = next((post for post in posts if not post["hasparent"]), posts[0])
    forum_names = {f["id"]: f["name"] for f in await _forums(campus, [answer["courseid"]])}
    course_names = {c.id: c.nombre for c in await campus.courses("all")}
    return Debate(
        titulo=first["subject"],
        foro=forum_names.get(answer["forumid"]),
        asignatura=course_names.get(answer["courseid"]),
        asignatura_id=answer["courseid"],
        url=discussion_url(campus.site, discussion_id),
        mensajes=[_post(post) for post in posts],
    )


async def _forums(campus: Campus, course_ids: list[int]) -> list[dict[str, Any]]:
    return await campus.call("mod_forum_get_forums_by_courses", courseids=course_ids)


def _announcement(
    campus: Campus,
    forum: dict[str, Any],
    discussion: dict[str, Any],
    course_names: dict[int, str],
) -> Aviso:
    # In this list, "id" is the first post and "discussion" the discussion itself.
    replies = discussion["numreplies"]
    return Aviso(
        asignatura=course_names.get(forum["course"]),
        asignatura_id=forum["course"],
        foro=forum["name"],
        titulo=discussion["name"],
        autor=discussion.get("userfullname"),
        fecha=iso_datetime(discussion["created"]),
        ultima_respuesta=iso_datetime(discussion["timemodified"]) if replies else None,
        mensaje=short_text(discussion["message"], MESSAGE_PREVIEW_CHARS) or "",
        respuestas=replies,
        fijado=discussion["pinned"],
        debate_id=discussion["discussion"],
        url=discussion_url(campus.site, discussion["discussion"]),
    )


def _post(post: dict[str, Any]) -> MensajeForo:
    author = post.get("author") or {}
    return MensajeForo(
        id=post["id"],
        autor=author.get("fullname"),
        fecha=iso_datetime(post["timecreated"]),
        asunto=post["subject"],
        mensaje=html_to_text(post["message"]),
        en_respuesta_a=post.get("parentid") or None,
        privado=post["isprivatereply"],
        adjuntos=[attachment["filename"] for attachment in post.get("attachments", [])],
    )
