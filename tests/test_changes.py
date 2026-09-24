from helpers import COURSES, DAY, NOW, FakeMoodle, load_fixture

from cvuex_mcp.campus import Campus
from cvuex_mcp.campus.changes import course_changes

UPDATES = "core_course_get_updates_since"
CONTENTS = "core_course_get_contents"
NO_UPDATES = {"instances": [], "warnings": []}


def campus_with_updates(updates_32338=None) -> tuple[Campus, FakeMoodle]:
    updates = updates_32338 or load_fixture(UPDATES)
    fake = FakeMoodle(
        {
            COURSES: load_fixture(COURSES),
            UPDATES: lambda form: updates if form["courseid"] == "32338" else NO_UPDATES,
            CONTENTS: load_fixture(f"{CONTENTS}__32338"),
        }
    )
    return Campus(fake.client()), fake


async def test_changes():
    """Real data: a new discussion in a course forum."""
    campus, fake = campus_with_updates()
    result = await course_changes(campus, since=NOW - 7 * DAY)

    assert result.desde == "2026-09-17T18:00+02:00"
    [course] = result.asignaturas
    assert course.asignatura_id == 32338
    [news] = course.novedades
    assert news.model_dump() == {
        "actividad": "Foro general de la asignatura",
        "tipo": "foro",
        "cambios": [
            "cambios en la actividad o su descripción",
            "debates nuevos o con respuestas nuevas (1)",
        ],
        "fecha": "2026-09-22T11:51+02:00",
        "url": "https://campusvirtual.unex.es/zonauex/avuex/mod/forum/view.php?id=1826525",
    }
    update_calls = [call for call in fake.calls if call["wsfunction"] == UPDATES]
    assert [call["courseid"] for call in update_calls] == ["32338", "32337", "32327"]
    assert {call["since"] for call in update_calls} == {str(NOW - 7 * DAY)}
    # Contents are only needed for courses with changes.
    assert [call["courseid"] for call in fake.calls if call["wsfunction"] == CONTENTS] == ["32338"]


async def test_changes_in_activity_not_visible_to_student():
    updates = {"instances": [{"contextlevel": "module", "id": 999, "updates": [{"name": "x"}]}]}
    campus, _ = campus_with_updates(updates)
    [course] = (await course_changes(campus, since=NOW)).asignaturas
    [news] = course.novedades
    assert (news.actividad, news.tipo, news.cambios, news.fecha) == (
        "Actividad 999 (no visible)",
        "otro",
        ["x"],
        None,
    )
    assert news.url.endswith("/course/view.php?id=32338")


async def test_changes_of_one_course():
    campus, fake = campus_with_updates()
    await course_changes(campus, since=NOW, course_id=32337)
    assert fake.calls[0]["classification"] == "all"
    assert [call["courseid"] for call in fake.calls if call["wsfunction"] == UPDATES] == ["32337"]
