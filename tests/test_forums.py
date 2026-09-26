import copy

import pytest
from helpers import COURSES, DAY, NOW, FakeMoodle, load_fixture

from cvuex_mcp.campus import Campus
from cvuex_mcp.campus.forums import DiscussionNotFoundError, announcements, read_discussion
from cvuex_mcp.moodle import InvalidTokenError

FORUMS = "mod_forum_get_forums_by_courses"
DISCUSSIONS = "mod_forum_get_forum_discussions"
POSTS = "mod_forum_get_discussion_posts"
NO_DISCUSSIONS = {"discussions": [], "warnings": []}
URL = "https://campusvirtual.unex.es/zonauex/avuex"


def campus_with_forums(forums=None, discussions=None) -> tuple[Campus, FakeMoodle]:
    """Real data by default: one announcement, in the forum of course 32338."""
    discussions = discussions or {"72401": load_fixture(DISCUSSIONS)}
    fake = FakeMoodle(
        {
            COURSES: load_fixture(COURSES),
            FORUMS: forums or load_fixture(FORUMS),
            DISCUSSIONS: lambda form: discussions.get(form["forumid"], NO_DISCUSSIONS),
            POSTS: load_fixture(POSTS),
        }
    )
    return Campus(fake.client(), clock=lambda: NOW), fake


def discussion(timemodified: int, name: str, **changes) -> dict:
    """The real announcement, moved in time."""
    answer = load_fixture(DISCUSSIONS)
    answer["discussions"][0].update(
        {"timemodified": timemodified, "created": timemodified, "name": name} | changes
    )
    return answer


async def test_announcements():
    campus, fake = campus_with_forums()
    result = await announcements(campus, days=30, limit=20)

    assert result.desde == "2026-08-25T18:00+02:00"
    [announcement] = result.avisos
    assert announcement.model_dump(exclude={"mensaje"}) == {
        "asignatura": "APRENDIZAJE AUTOMÁTICO Y APRENDIZAJE PROFUNDO",
        "asignatura_id": 32338,
        "foro": "Foro general de la asignatura",
        "titulo": "Comienzo de clases de la Asignatura de Aprendizaje Automático y Profundo",
        "autor": "Persona 1",
        "fecha": "2026-09-23T20:16+02:00",
        "ultima_respuesta": None,
        "respuestas": 0,
        "fijado": False,
        "debate_id": 41804,
        "url": f"{URL}/mod/forum/discuss.php?d=41804",
    }
    assert announcement.mensaje.startswith("La asignatura de Aprendizaje Automático")
    assert "<p>" not in announcement.mensaje

    [forums_call] = [call for call in fake.calls if call["wsfunction"] == FORUMS]
    assert [forums_call[f"courseids[{i}]"] for i in range(3)] == ["32338", "32337", "32327"]
    discussion_calls = [call for call in fake.calls if call["wsfunction"] == DISCUSSIONS]
    assert len(discussion_calls) == 5  # every forum in the fixture
    assert {(c["sortorder"], c["page"], c["perpage"]) for c in discussion_calls} == {
        ("1", "0", "20")
    }


async def test_announcements_of_one_course():
    campus, fake = campus_with_forums()
    await announcements(campus, days=30, limit=20, course_id=32337)
    [forums_call] = [call for call in fake.calls if call["wsfunction"] == FORUMS]
    assert forums_call["courseids[0]"] == "32337"
    assert "courseids[1]" not in forums_call


async def test_old_announcements_are_left_out():
    campus, _ = campus_with_forums(discussions={"72401": discussion(NOW - 3 * DAY, "Viejo")})
    assert (await announcements(campus, days=2, limit=20)).avisos == []


async def test_announcements_from_all_forums_newest_first_up_to_the_limit():
    campus, _ = campus_with_forums(
        discussions={
            "72401": discussion(NOW - 5 * DAY, "Hace cinco días"),
            "72400": discussion(NOW - DAY, "Ayer"),
            "72380": discussion(NOW - 2 * DAY, "Anteayer"),
        }
    )
    result = await announcements(campus, days=30, limit=2)
    assert [a.titulo for a in result.avisos] == ["Ayer", "Anteayer"]
    assert [a.foro for a in result.avisos] == ["Avisos", "Avisos"]


async def test_only_announcement_and_general_forums_are_read():
    forums = load_fixture(FORUMS)
    forums[1]["type"] = "general"
    forums[2]["type"] = "qanda"
    campus, fake = campus_with_forums(forums=forums)
    await announcements(campus, days=30, limit=20)
    read = [call["forumid"] for call in fake.calls if call["wsfunction"] == DISCUSSIONS]
    assert read == ["72401", "72400", "72256", "72249"]


async def test_answered_announcement_shows_the_last_reply():
    answer = discussion(NOW - DAY, "Con respuestas", numreplies=2, created=NOW - 10 * DAY)
    campus, _ = campus_with_forums(discussions={"72401": answer})
    [announcement] = (await announcements(campus, days=7, limit=20)).avisos
    assert announcement.respuestas == 2
    assert announcement.fecha == "2026-09-14T18:00+02:00"
    assert announcement.ultima_respuesta == "2026-09-23T18:00+02:00"


async def test_hidden_author():
    answer = discussion(NOW - DAY, "Anónimo", userfullname=None)
    campus, _ = campus_with_forums(discussions={"72401": answer})
    [announcement] = (await announcements(campus, days=7, limit=20)).avisos
    assert announcement.autor is None


async def test_read_discussion():
    campus, fake = campus_with_forums()
    result = await read_discussion(campus, 41804)

    assert result.model_dump(exclude={"mensajes"}) == {
        "titulo": "Comienzo de clases de la Asignatura de Aprendizaje Automático y Profundo",
        "foro": "Foro general de la asignatura",
        "asignatura": "APRENDIZAJE AUTOMÁTICO Y APRENDIZAJE PROFUNDO",
        "asignatura_id": 32338,
        "url": f"{URL}/mod/forum/discuss.php?d=41804",
    }
    [post] = result.mensajes
    assert post.model_dump(exclude={"mensaje"}) == {
        "id": 64213,
        "autor": "Persona 1",
        "fecha": "2026-09-23T20:16+02:00",
        "asunto": "Comienzo de clases de la Asignatura de Aprendizaje Automático y Profundo",
        "en_respuesta_a": None,
        "privado": False,
        "adjuntos": [],
    }
    assert post.mensaje.endswith("Os enviaremos un enlace.\n\nPersona 2 y Persona 1")

    [posts_call] = [call for call in fake.calls if call["wsfunction"] == POSTS]
    assert (posts_call["discussionid"], posts_call["sortby"], posts_call["sortdirection"]) == (
        "41804",
        "created",
        "ASC",
    )


async def test_read_discussion_with_replies():
    answer = load_fixture(POSTS)
    first = answer["posts"][0]
    reply = copy.deepcopy(first) | {
        "id": 64300,
        "subject": "Re: Comienzo de clases",
        "message": "<p>¿Habrá grabación?</p>",
        "hasparent": True,
        "parentid": 64213,
        "timecreated": first["timecreated"] + 3600,
        "isprivatereply": True,
        "attachments": [{"filename": "horario.pdf"}],
    }
    answer["posts"].append(reply)
    campus, fake = campus_with_forums()
    fake.answers[POSTS] = answer

    result = await read_discussion(campus, 41804)
    assert result.titulo == first["subject"]
    assert [p.id for p in result.mensajes] == [64213, 64300]
    reply_post = result.mensajes[1]
    assert (reply_post.mensaje, reply_post.en_respuesta_a) == ("¿Habrá grabación?", 64213)
    assert (reply_post.privado, reply_post.adjuntos) == (True, ["horario.pdf"])


UNKNOWN_DISCUSSION = {
    "exception": "Error",
    "errorcode": "unknown",
    "message": "Call to a member function get_forum_id() on null",
}


async def test_unknown_discussion():
    """Real answer for a discussion id that doesn't exist."""
    campus, fake = campus_with_forums()
    fake.answers[POSTS] = UNKNOWN_DISCUSSION
    with pytest.raises(DiscussionNotFoundError, match="debate 1:"):
        await read_discussion(campus, 1)


async def test_expired_session_while_reading_a_discussion():
    campus, fake = campus_with_forums()
    fake.answers[POSTS] = UNKNOWN_DISCUSSION | {"errorcode": "invalidtoken"}
    with pytest.raises(InvalidTokenError):
        await read_discussion(campus, 41804)


async def test_announcement_shown_from_a_later_date():
    """Seen on the campus: Moodle dates a discussion from when it starts to be shown."""
    answer = discussion(NOW - DAY, "Programado", created=NOW - 30 * DAY, timestart=NOW - DAY)
    campus, _ = campus_with_forums(discussions={"72401": answer})
    [announcement] = (await announcements(campus, days=7, limit=20)).avisos
    assert announcement.fecha == "2026-09-23T18:00+02:00"
