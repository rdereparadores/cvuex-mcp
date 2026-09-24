import pytest
from helpers import FakeMoodle, load_fixture

from cvuex_mcp import campus as campus_module
from cvuex_mcp.campus import ALLOWED_FUNCTIONS, Campus, FunctionNotAllowedError
from cvuex_mcp.moodle import InvalidTokenError

SITE_INFO = "core_webservice_get_site_info"


@pytest.fixture
def fake_moodle() -> FakeMoodle:
    return FakeMoodle({SITE_INFO: load_fixture(SITE_INFO)})


async def test_site_info(fake_moodle):
    info = await Campus(fake_moodle.client()).site_info()
    assert info.full_name == "Persona 4"
    assert info.user_id == 1001
    assert info.site_name == "Aulas regladas (AVUEx)"


async def test_user_id_reuses_cached_site_info(fake_moodle):
    campus = Campus(fake_moodle.client())
    await campus.site_info()
    assert await campus.user_id() == 1001
    assert fake_moodle.functions_called() == [SITE_INFO]


async def test_functions_outside_the_allowlist_are_never_sent(fake_moodle):
    campus = Campus(fake_moodle.client())
    with pytest.raises(FunctionNotAllowedError):
        await campus._call("mod_assign_save_submission", assignmentid=1)
    assert fake_moodle.calls == []


def test_allowlist_has_only_read_functions():
    for function in ALLOWED_FUNCTIONS:
        assert "_get_" in function, function
        assert "_view_" not in function, function


COURSES = "core_course_get_enrolled_courses_by_timeline_classification"


async def test_courses():
    fake = FakeMoodle({COURSES: load_fixture(COURSES)})
    courses = await Campus(fake.client()).courses("inprogress")

    assert [course.id for course in courses] == [32338, 32337, 32327]
    first = courses[0]
    assert first.nombre == "APRENDIZAJE AUTOMÁTICO Y APRENDIZAJE PROFUNDO"
    assert first.titulacion == "Máster Universitario en Ingeniería Informática"
    assert first.url == "https://campusvirtual.unex.es/zonauex/avuex/course/view.php?id=32338"
    assert fake.calls[0]["classification"] == "inprogress"


async def test_course_progress_only_when_moodle_tracks_it():
    answer = load_fixture(COURSES)
    untracked, tracked, *_ = answer["courses"]
    untracked |= {"hasprogress": False, "progress": 0}
    tracked |= {"hasprogress": True, "progress": 66.6667}

    courses = await Campus(FakeMoodle({COURSES: answer}).client()).courses("all")
    assert [course.progreso for course in courses[:2]] == [None, 67]


BY_TIMESORT = "core_calendar_get_action_events_by_timesort"
BY_COURSE = "core_calendar_get_action_events_by_course"
EVENTS = load_fixture(f"{BY_TIMESORT}__sintetico")
NOW = 1790265600  # 2026-09-24 18:00, Spanish time
DAY = 24 * 60 * 60


def campus_with_events(answer=EVENTS, *, clock=lambda: NOW) -> tuple[Campus, FakeMoodle]:
    fake = FakeMoodle({BY_TIMESORT: answer, BY_COURSE: answer})
    return Campus(fake.client(), clock=clock), fake


async def test_deadlines():
    campus, fake = campus_with_events()
    result = await campus.deadlines(days=14)

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
        "accion": "Añadir entrega",
        "vencido": False,
        "url": "https://campusvirtual.unex.es/zonauex/avuex/mod/assign/view.php?id=1830001",
    }
    assert (quiz.tipo, quiz.accion) == ("cuestionario", "Intente resolver el cuestionario ahora")

    [call] = fake.calls
    assert call["wsfunction"] == BY_TIMESORT
    assert int(call["timesortfrom"]) == NOW - 30 * DAY
    assert int(call["timesortto"]) == NOW + 14 * DAY
    assert call["limitnum"] == "50"


async def test_deadlines_of_one_course():
    campus, fake = campus_with_events()
    await campus.deadlines(days=7, course_id=32337)
    assert fake.calls[0]["wsfunction"] == BY_COURSE
    assert fake.calls[0]["courseid"] == "32337"


async def test_deadlines_without_actionable_action():
    answer = load_fixture(f"{BY_TIMESORT}__sintetico")
    answer["events"][1]["action"]["actionable"] = False
    answer["events"][2]["action"] = None
    campus, _ = campus_with_events(answer)
    result = await campus.deadlines(days=14)
    assert [plazo.accion for plazo in result.plazos[1:]] == [None, None]


async def test_deadlines_reuse_cache_within_the_same_minute():
    now = [NOW + 5]
    campus, fake = campus_with_events(clock=lambda: now[0])
    await campus.deadlines(days=14)
    now[0] += 30
    await campus.deadlines(days=14)
    assert len(fake.calls) == 1


async def test_no_deadlines():
    campus, _ = campus_with_events(load_fixture(f"{BY_TIMESORT}__vacio"))
    assert (await campus.deadlines(days=14)).plazos == []


async def test_real_course_event_without_available_action():
    """A real choice that hasn't opened yet: Moodle sends a non-actionable action."""
    campus, _ = campus_with_events(load_fixture(BY_COURSE))
    [plazo] = (await campus.deadlines(days=90, course_id=32254)).plazos
    assert (plazo.tipo, plazo.fecha, plazo.accion) == ("consulta", "2026-11-28T00:00+01:00", None)


ASSIGNMENTS = "mod_assign_get_assignments"
STATUS = "mod_assign_get_submission_status"
STATUSES = load_fixture(f"{STATUS}__sintetico_por_tarea")


def campus_with_assignments(statuses=STATUSES) -> tuple[Campus, FakeMoodle]:
    fake = FakeMoodle(
        {
            COURSES: load_fixture(COURSES),
            ASSIGNMENTS: load_fixture(f"{ASSIGNMENTS}__sintetico"),
            STATUS: lambda form: statuses[form["assignid"]],
        }
    )
    return Campus(fake.client(), clock=lambda: NOW), fake


async def test_pending_submissions():
    campus, fake = campus_with_assignments()
    result = await campus.submissions()

    assert [(e.tarea, e.estado) for e in result.entregas] == [
        ("Práctica 1: regresión lineal", "borrador"),
        ("Proyecto final (en grupo)", "sin_entregar"),  # from the group's submission
    ]
    assert result.avisos == []
    # Looks at the courses in progress.
    assignments_call = fake.calls[1]
    assert assignments_call["wsfunction"] == ASSIGNMENTS
    assert [assignments_call[f"courseids[{i}]"] for i in range(3)] == ["32338", "32337", "32327"]


async def test_all_submissions_with_feedback():
    campus, _ = campus_with_assignments()
    result = await campus.submissions(only_pending=False)

    graded, draft, exam, project = result.entregas  # by due date
    assert graded.model_dump() == {
        "tarea": "Práctica 0: entorno de trabajo",
        "asignatura": "APRENDIZAJE AUTOMÁTICO Y APRENDIZAJE PROFUNDO",
        "asignatura_id": 32338,
        "fecha_limite": "2026-09-21T18:00+02:00",
        "vencida": True,
        "estado": "entregada",
        "puede_entregar": False,
        "calificacion": "8,50 / 10,00",
        "comentarios_profesor": "Buen trabajo. Revisa la normalización de los datos.",
        "url": "https://campusvirtual.unex.es/zonauex/avuex/mod/assign/view.php?id=1830102",
    }
    assert (draft.vencida, draft.puede_entregar, draft.calificacion) == (False, True, None)
    assert (exam.estado, exam.asignatura) == ("sin_entrega_online", "COMPUTACIÓN GRÁFICA")
    assert project.fecha_limite == "2026-11-28T00:00+01:00"


async def test_submissions_of_one_course():
    campus, fake = campus_with_assignments()
    await campus.submissions(32338)
    assert fake.functions_called()[0] == ASSIGNMENTS  # no need to list courses
    assert fake.calls[0]["courseids[0]"] == "32338"


async def test_extension_replaces_due_date():
    statuses = load_fixture(f"{STATUS}__sintetico_por_tarea")
    statuses["7101"]["lastattempt"]["extensionduedate"] = 1790632740
    campus, _ = campus_with_assignments(statuses)
    draft, _ = (await campus.submissions()).entregas
    assert draft.fecha_limite == "2026-09-28T23:59+02:00"


async def test_one_failing_assignment_does_not_hide_the_rest():
    statuses = load_fixture(f"{STATUS}__sintetico_por_tarea")
    statuses["7103"] = {"exception": "x", "errorcode": "nopermissions", "message": "Sin permiso"}
    campus, _ = campus_with_assignments(statuses)
    result = await campus.submissions()
    assert [e.tarea for e in result.entregas] == ["Práctica 1: regresión lineal"]
    assert result.avisos == ["No se pudo consultar 'Proyecto final (en grupo)': Sin permiso"]


async def test_expired_session_is_not_hidden_as_a_warning():
    expired = {"exception": "x", "errorcode": "invalidtoken", "message": ""}
    campus, _ = campus_with_assignments(dict.fromkeys(STATUSES, expired))
    with pytest.raises(InvalidTokenError):
        await campus.submissions()


async def test_only_the_closest_assignments_are_checked(monkeypatch):
    monkeypatch.setattr(campus_module, "MAX_ASSIGNMENTS", 2)
    campus, fake = campus_with_assignments()
    result = await campus.submissions(only_pending=False)

    checked = [call["assignid"] for call in fake.calls if call["wsfunction"] == STATUS]
    assert checked == ["7101", "7102"]  # due in 2 days and 3 days ago
    assert "Hay 4 tareas" in result.avisos[0]


async def test_no_courses_no_requests():
    fake = FakeMoodle({COURSES: {"courses": [], "nextoffset": 0}})
    result = await Campus(fake.client()).submissions()
    assert result.entregas == []
    assert fake.functions_called() == [COURSES]


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
    result = await campus.changes(since=NOW - 7 * DAY)

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
    [course] = (await campus.changes(since=NOW)).asignaturas
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
    await campus.changes(since=NOW, course_id=32337)
    assert fake.calls[0]["classification"] == "all"
    assert [call["courseid"] for call in fake.calls if call["wsfunction"] == UPDATES] == ["32337"]
