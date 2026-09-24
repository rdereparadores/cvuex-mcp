import pytest
from helpers import COURSES, NOW, FakeMoodle, load_fixture

from cvuex_mcp.campus import Campus
from cvuex_mcp.campus import assignments as assignments_module
from cvuex_mcp.campus.assignments import submission_statuses
from cvuex_mcp.moodle import InvalidTokenError

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
    result = await submission_statuses(campus)

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
    result = await submission_statuses(campus, only_pending=False)

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
    await submission_statuses(campus, 32338)
    assert fake.functions_called()[0] == ASSIGNMENTS  # no need to list courses
    assert fake.calls[0]["courseids[0]"] == "32338"


async def test_extension_replaces_due_date():
    statuses = load_fixture(f"{STATUS}__sintetico_por_tarea")
    statuses["7101"]["lastattempt"]["extensionduedate"] = 1790632740
    campus, _ = campus_with_assignments(statuses)
    draft, _ = (await submission_statuses(campus)).entregas
    assert draft.fecha_limite == "2026-09-28T23:59+02:00"


async def test_one_failing_assignment_does_not_hide_the_rest():
    statuses = load_fixture(f"{STATUS}__sintetico_por_tarea")
    statuses["7103"] = {"exception": "x", "errorcode": "nopermissions", "message": "Sin permiso"}
    campus, _ = campus_with_assignments(statuses)
    result = await submission_statuses(campus)
    assert [e.tarea for e in result.entregas] == ["Práctica 1: regresión lineal"]
    assert result.avisos == ["No se pudo consultar 'Proyecto final (en grupo)': Sin permiso"]


async def test_expired_session_is_not_hidden_as_a_warning():
    expired = {"exception": "x", "errorcode": "invalidtoken", "message": ""}
    campus, _ = campus_with_assignments(dict.fromkeys(STATUSES, expired))
    with pytest.raises(InvalidTokenError):
        await submission_statuses(campus)


async def test_only_the_closest_assignments_are_checked(monkeypatch):
    monkeypatch.setattr(assignments_module, "MAX_ASSIGNMENTS", 2)
    campus, fake = campus_with_assignments()
    result = await submission_statuses(campus, only_pending=False)

    checked = [call["assignid"] for call in fake.calls if call["wsfunction"] == STATUS]
    assert checked == ["7101", "7102"]  # due in 2 days and 3 days ago
    assert "Hay 4 tareas" in result.avisos[0]


async def test_no_courses_no_requests():
    fake = FakeMoodle({COURSES: {"courses": [], "nextoffset": 0}})
    result = await submission_statuses(Campus(fake.client()))
    assert result.entregas == []
    assert fake.functions_called() == [COURSES]
