from datetime import UTC, datetime, timedelta

import pytest
from helpers import COURSES, DAY, NOW, FakeMoodle, load_fixture
from icalendar import Calendar

from cvuex_mcp.calendar_export import export_calendar
from cvuex_mcp.campus import Campus, CourseNotEnrolledError

BY_TIMESORT = "core_calendar_get_action_events_by_timesort"
BY_COURSE = "core_calendar_get_action_events_by_course"
CALENDAR = "core_calendar_get_calendar_events"
SITE = "campusvirtual.unex.es/zonauex/avuex"
PERSONAL = {
    "id": 5,
    "name": "Repaso: tema 1, 2; y 3",
    "description": "",
    "courseid": 0,
    "eventtype": "user",
    "modulename": None,
    "timestart": NOW + DAY,
    "timeduration": 1800,
}


def campus_with_events(calendar_events: list | None = None) -> tuple[Campus, FakeMoodle]:
    """Synthetic pending events (one of them overdue) and a personal event."""
    fake = FakeMoodle(
        {
            BY_TIMESORT: load_fixture(f"{BY_TIMESORT}__sintetico"),
            BY_COURSE: load_fixture(f"{BY_TIMESORT}__sintetico"),
            CALENDAR: {"events": [PERSONAL] if calendar_events is None else calendar_events},
            COURSES: load_fixture(COURSES),
        }
    )
    return Campus(fake.client(), clock=lambda: NOW), fake


def read_events(path) -> list:
    return Calendar.from_ical(path.read_bytes()).walk("VEVENT")


async def test_export(tmp_path):
    campus, fake = campus_with_events()
    path = tmp_path / "calendario.ics"
    result = await export_calendar(campus, 30, None, path)

    assert (result.fichero, result.eventos) == (str(path), 3)
    assert (result.desde, result.hasta) == ("2026-09-24T18:00+02:00", "2026-10-24T18:00+02:00")
    [call] = [call for call in fake.calls if call["wsfunction"] == BY_TIMESORT]
    assert int(call["timesortfrom"]) == NOW  # nothing overdue is asked for...

    personal, assignment, quiz = read_events(path)  # ...nor written, in date order
    assert [str(event["uid"]) for event in (personal, assignment, quiz)] == [
        f"5@{SITE}",
        f"90001@{SITE}",
        f"90002@{SITE}",
    ]
    assert str(assignment["summary"]) == (
        "Práctica 1: regresión lineal está en fecha de entrega "
        "(APRENDIZAJE AUTOMÁTICO Y APRENDIZAJE PROFUNDO)"
    )
    assert assignment.decoded("dtstart") == datetime(2026, 9, 26, 21, 59, tzinfo=UTC)
    assert assignment.decoded("dtend") == assignment.decoded("dtstart")
    assert assignment.decoded("description") == (
        "Asignatura: APRENDIZAJE AUTOMÁTICO Y APRENDIZAJE PROFUNDO\n"
        "Tipo: tarea\n"
        "Qué hacer: Añadir entrega\n"
        "Entrega el cuaderno .ipynb con los resultados.\n"
        "https://campusvirtual.unex.es/zonauex/avuex/mod/assign/view.php?id=1830001"
    )
    assert str(assignment["url"]).endswith("/mod/assign/view.php?id=1830001")


async def test_events_keep_their_duration_and_special_characters(tmp_path):
    campus, _ = campus_with_events()
    await export_calendar(campus, 30, None, tmp_path / "calendario.ics")
    personal = read_events(tmp_path / "calendario.ics")[0]

    assert str(personal["summary"]) == "Repaso: tema 1, 2; y 3"  # no course
    assert personal.decoded("dtend") - personal.decoded("dtstart") == timedelta(minutes=30)


async def test_uids_are_stable_between_exports(tmp_path):
    campus, _ = campus_with_events()
    path = tmp_path / "calendario.ics"
    await export_calendar(campus, 30, None, path)
    first = [str(event["uid"]) for event in read_events(path)]
    await export_calendar(campus, 60, None, path)  # the file is replaced
    assert [str(event["uid"]) for event in read_events(path)] == first


async def test_nothing_coming_up(tmp_path):
    campus, fake = campus_with_events(calendar_events=[])
    fake.answers[BY_TIMESORT] = load_fixture(f"{BY_TIMESORT}__vacio")
    result = await export_calendar(campus, 30, None, tmp_path / "calendario.ics")
    assert result.eventos == 0
    assert read_events(tmp_path / "calendario.ics") == []


async def test_one_course(tmp_path):
    campus, fake = campus_with_events()
    await export_calendar(campus, 30, 32338, tmp_path / "calendario.ics")
    [call] = [call for call in fake.calls if call["wsfunction"] == BY_COURSE]
    assert call["courseid"] == "32338"


async def test_a_course_not_enrolled_in(tmp_path):
    campus, _ = campus_with_events()
    with pytest.raises(CourseNotEnrolledError):
        await export_calendar(campus, 30, 32000, tmp_path / "calendario.ics")
    assert not (tmp_path / "calendario.ics").exists()
