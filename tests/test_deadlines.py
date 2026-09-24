from helpers import COURSES, DAY, NOW, FakeMoodle, load_fixture

from cvuex_mcp.campus import Campus
from cvuex_mcp.campus.deadlines import upcoming_deadlines

BY_TIMESORT = "core_calendar_get_action_events_by_timesort"
BY_COURSE = "core_calendar_get_action_events_by_course"
EVENTS = load_fixture(f"{BY_TIMESORT}__sintetico")


CALENDAR = "core_calendar_get_calendar_events"
NO_CALENDAR_EVENTS = {"events": [], "warnings": []}


def campus_with_events(
    answer=EVENTS, *, calendar=NO_CALENDAR_EVENTS, courses=None, clock=lambda: NOW
) -> tuple[Campus, FakeMoodle]:
    fake = FakeMoodle(
        {
            BY_TIMESORT: answer,
            BY_COURSE: answer,
            CALENDAR: calendar,
            COURSES: courses or load_fixture(COURSES),
        }
    )
    return Campus(fake.client(), clock=clock), fake


async def test_deadlines():
    campus, fake = campus_with_events()
    result = await upcoming_deadlines(campus, days=14)

    assert (result.desde, result.hasta) == ("2026-08-25T18:00+02:00", "2026-10-08T18:00+02:00")
    overdue, assignment, quiz = result.plazos
    assert overdue.vencido and not assignment.vencido and not quiz.vencido
    assert assignment.model_dump() == {
        "fecha": "2026-09-26T23:59+02:00",
        "asignatura": "APRENDIZAJE AUTOMÁTICO Y APRENDIZAJE PROFUNDO",
        "asignatura_id": 32338,
        "actividad": "Práctica 1: regresión lineal",
        "tipo": "tarea",
        "evento": "Práctica 1: regresión lineal está en fecha de entrega",
        "descripcion": "Entrega el cuaderno .ipynb con los resultados.",
        "requiere_accion": True,
        "accion": "Añadir entrega",
        "vencido": False,
        "url": "https://campusvirtual.unex.es/zonauex/avuex/mod/assign/view.php?id=1830001",
    }
    assert (quiz.tipo, quiz.accion) == ("cuestionario", "Intente resolver el cuestionario ahora")

    call = fake.calls[0]
    assert call["wsfunction"] == BY_TIMESORT
    assert int(call["timesortfrom"]) == NOW - 30 * DAY
    assert int(call["timesortto"]) == NOW + 14 * DAY
    assert call["limitnum"] == "50"


async def test_deadlines_of_one_course():
    campus, fake = campus_with_events()
    await upcoming_deadlines(campus, days=7, course_id=32337)
    assert fake.calls[0]["wsfunction"] == BY_COURSE
    assert fake.calls[0]["courseid"] == "32337"


async def test_deadlines_without_actionable_action():
    answer = load_fixture(f"{BY_TIMESORT}__sintetico")
    answer["events"][1]["action"]["actionable"] = False
    answer["events"][2]["action"] = None
    campus, _ = campus_with_events(answer)
    result = await upcoming_deadlines(campus, days=14)
    assert [plazo.accion for plazo in result.plazos[1:]] == [None, None]


async def test_deadlines_reuse_cache_within_the_same_minute():
    now = [NOW + 5]
    campus, fake = campus_with_events(clock=lambda: now[0])
    await upcoming_deadlines(campus, days=14)
    requests_first_time = len(fake.calls)
    now[0] += 30
    await upcoming_deadlines(campus, days=14)
    assert len(fake.calls) == requests_first_time


async def test_no_deadlines():
    campus, _ = campus_with_events(load_fixture(f"{BY_TIMESORT}__vacio"))
    assert (await upcoming_deadlines(campus, days=14)).plazos == []


async def test_real_course_event_without_available_action():
    """A real choice that hasn't opened yet: Moodle sends a non-actionable action."""
    campus, _ = campus_with_events(load_fixture(BY_COURSE))
    [plazo] = (await upcoming_deadlines(campus, days=90, course_id=32254)).plazos
    assert (plazo.tipo, plazo.fecha, plazo.accion) == ("consulta", "2026-11-28T00:00+01:00", None)


SRP_COURSES = {
    "courses": [
        {
            "id": 32254,
            "fullname": "Sistemas de Recomendación y Predicción",
            "coursecategory": "Máster Universitario en Ingeniería Informática",
            "hasprogress": False,
            "progress": 0,
        }
    ]
}


async def test_calendar_events_are_added_without_duplicates():
    """Real data: a choice opens on 28/09 (no action) and closes on 28/11 (pending)."""
    campus, _ = campus_with_events(
        load_fixture(BY_COURSE), calendar=load_fixture(CALENDAR), courses=SRP_COURSES
    )
    opening, closing = (await upcoming_deadlines(campus, days=90, course_id=32254)).plazos

    assert opening.model_dump() == {
        "fecha": "2026-09-28T00:00+02:00",
        "asignatura": "Sistemas de Recomendación y Predicción",
        "asignatura_id": 32254,
        "actividad": "Selección tipo de evaluación GLOBAL: abren",
        "tipo": "consulta",
        "evento": "Selección tipo de evaluación GLOBAL: abren",
        "descripcion": (
            "Seleccionar solo en caso de no querer evaluación contínua. Quienes seleccionen "
            "esta opción tendrán que presentarse a los correspondientes exámenes finales, "
            "tanto teóricos como prácticos."
        ),
        "requiere_accion": False,
        "accion": None,
        "vencido": False,
        "url": "https://campusvirtual.unex.es/zonauex/avuex/calendar/view.php"
        "?view=day&course=32254&time=1790546400#event_252162",
    }
    assert (closing.evento, closing.requiere_accion) == (
        "Selección tipo de evaluación GLOBAL: cierran",
        True,
    )


async def test_calendar_request_for_all_courses_includes_personal_events():
    campus, fake = campus_with_events()
    await upcoming_deadlines(campus, days=14)
    [call] = [call for call in fake.calls if call["wsfunction"] == CALENDAR]
    assert [call[f"events[courseids][{i}]"] for i in range(3)] == ["32338", "32337", "32327"]
    assert (call["options[timestart]"], call["options[timeend]"]) == (str(NOW), str(NOW + 14 * DAY))
    assert (call["options[userevents]"], call["options[siteevents]"]) == ("1", "1")


async def test_calendar_request_for_one_course():
    campus, fake = campus_with_events()
    await upcoming_deadlines(campus, days=14, course_id=32254)
    [call] = [call for call in fake.calls if call["wsfunction"] == CALENDAR]
    assert call["events[courseids][0]"] == "32254"
    assert (call["options[userevents]"], call["options[siteevents]"]) == ("0", "0")


async def test_personal_calendar_event():
    personal = {
        "id": 5,
        "name": "Tutoría con el profesor",
        "description": "",
        "courseid": 0,
        "eventtype": "user",
        "modulename": None,
        "timestart": NOW + DAY,
        "timeduration": 1800,
    }
    campus, _ = campus_with_events(calendar={"events": [personal], "warnings": []})
    plazos = (await upcoming_deadlines(campus, days=14)).plazos
    [plazo] = [p for p in plazos if p.evento == "Tutoría con el profesor"]

    assert (plazo.tipo, plazo.asignatura, plazo.asignatura_id, plazo.descripcion) == (
        "evento personal",
        None,
        None,
        None,
    )
    assert "course=1&" in plazo.url
