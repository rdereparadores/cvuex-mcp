import pytest
from helpers import COURSES, FakeMoodle, load_fixture

from cvuex_mcp.campus import Campus
from cvuex_mcp.campus.grades import CourseGradesNotAvailableError, course_grades, grades_overview
from cvuex_mcp.moodle import MoodleError

SITE_INFO = "core_webservice_get_site_info"
OVERVIEW = "gradereport_overview_get_course_grades"
GRADE_ITEMS = "gradereport_user_get_grade_items"
CATEGORIES = "core_grades_get_gradeitems"
URL = "https://campusvirtual.unex.es/zonauex/avuex"


def campus_with_grades(real: bool = False) -> tuple[Campus, FakeMoodle]:
    """Synthetic grades by default; the real ones are all still empty."""
    variant = "vacio" if real else "sintetico"
    fake = FakeMoodle(
        {
            SITE_INFO: load_fixture(SITE_INFO),
            COURSES: load_fixture(COURSES),
            OVERVIEW: load_fixture(OVERVIEW if real else f"{OVERVIEW}__sintetico"),
            GRADE_ITEMS: load_fixture(f"{GRADE_ITEMS}__{variant}"),
            CATEGORIES: load_fixture(f"{CATEGORIES}__{variant}"),
        }
    )
    return Campus(fake.client()), fake


async def test_overview():
    campus, _ = campus_with_grades()
    result = await grades_overview(campus)

    assert [grade.model_dump() for grade in result.asignaturas] == [
        {
            "asignatura": "APRENDIZAJE AUTOMÁTICO Y APRENDIZAJE PROFUNDO",
            "asignatura_id": 32338,
            "nota": "7,40",
            "url": f"{URL}/grade/report/user/index.php?id=32338",
        },
        {
            "asignatura": "COMPUTACIÓN GRÁFICA",
            "asignatura_id": 32337,
            "nota": None,
            "url": f"{URL}/grade/report/user/index.php?id=32337",
        },
        {
            # A course not in the enrolled courses list (in the test data).
            "asignatura": None,
            "asignatura_id": 31000,
            "nota": "6,50",
            "url": f"{URL}/grade/report/user/index.php?id=31000",
        },
    ]
    assert result.detalle == []


async def test_overview_without_grades():
    """Real answer: every course, still without a grade."""
    campus, _ = campus_with_grades(real=True)
    result = await grades_overview(campus)
    assert len(result.asignaturas) == 5
    assert {grade.nota for grade in result.asignaturas} == {None}


async def test_course_grades():
    campus, fake = campus_with_grades()
    result = await course_grades(campus, 32338)

    [total] = result.asignaturas
    assert (total.asignatura_id, total.nota) == (32338, "7,40")
    assert [(item.actividad, item.tipo, item.categoria) for item in result.detalle] == [
        ("Práctica 1", "tarea", "Prácticas"),
        ("Práctica 2", "tarea", "Prácticas"),
        ("Total de Prácticas", "total de categoría", "Prácticas"),
        ("Test tema 1", "cuestionario", "Teoría"),
        ("Examen final", "ítem manual", "Teoría"),
        ("Total de Teoría", "total de categoría", "Teoría"),
        ("Asistencia", "ítem manual", None),  # directly in the course total
    ]
    assert result.detalle[0].model_dump() == {
        "actividad": "Práctica 1",
        "tipo": "tarea",
        "categoria": "Prácticas",
        "nota": "8,50",  # without the "passed" icon
        "rango": "0–10",
        "porcentaje": "85,00 %",
        "peso": "100,00 %",
        "comentarios": "Buen trabajo. Revisa los comentarios del código.",
        "fecha": "2026-09-22T20:00+02:00",
        "url": f"{URL}/mod/assign/view.php?id=1830001",
    }

    [grades_call] = [call for call in fake.calls if call["wsfunction"] == GRADE_ITEMS]
    assert (grades_call["courseid"], grades_call["userid"]) == ("32338", "1001")


async def test_ungraded_item():
    campus, _ = campus_with_grades()
    exam = (await course_grades(campus, 32338)).detalle[4]
    assert (exam.nota, exam.porcentaje, exam.comentarios, exam.fecha, exam.url) == (
        None,
        None,
        None,
        None,
        None,
    )
    assert exam.peso == "0,00 % (vacío: no cuenta hasta que tenga nota)"


async def test_empty_gradebook():
    """Real answer: only the course total, without a grade and without categories."""
    campus, fake = campus_with_grades(real=True)
    result = await course_grades(campus, 32338)
    assert result.asignaturas[0].nota is None
    assert result.detalle == []
    assert CATEGORIES not in fake.functions_called()  # no categories to name


async def test_course_not_enrolled():
    """Real answer for a course the student isn't enrolled in."""
    campus, fake = campus_with_grades()
    fake.answers[GRADE_ITEMS] = {
        "exception": "required_capability_exception",
        "errorcode": "nopermissions",
        "message": "Lo sentimos, pero no tiene los permisos para hacer esto (Ver informe...).",
    }
    with pytest.raises(CourseGradesNotAvailableError, match="asignatura 1\\."):
        await course_grades(campus, 1)


async def test_other_grade_errors_are_not_hidden():
    campus, fake = campus_with_grades()
    fake.answers[GRADE_ITEMS] = {"exception": "x", "errorcode": "servererror", "message": "Boom"}
    with pytest.raises(MoodleError, match="Boom"):
        await course_grades(campus, 32338)


async def test_categories_with_only_hidden_items():
    """Seen on the campus: categories whose items are all hidden from the student.

    Without visible items there is no name for them; without a grade, they are left out.
    """
    campus, fake = campus_with_grades()
    answer = load_fixture(f"{GRADE_ITEMS}__sintetico")
    items = answer["usergrades"][0]["gradeitems"]
    empty, graded = (dict(items[2], id=id, iteminstance=id) for id in (51990, 51991))
    empty["gradeformatted"] = "-"
    items[:0] = [empty, graded]
    fake.answers[GRADE_ITEMS] = answer

    detail = (await course_grades(campus, 32338)).detalle
    assert [item.actividad for item in detail[:2]] == ["Total de la categoría", "Práctica 1"]
    assert detail[0].nota == "8,50"


async def test_items_that_are_not_graded_have_no_range():
    """Seen on the campus: Moodle formats their range as a lone dash."""
    campus, fake = campus_with_grades()
    answer = load_fixture(f"{GRADE_ITEMS}__sintetico")
    answer["usergrades"][0]["gradeitems"][0]["rangeformatted"] = "&ndash;"
    fake.answers[GRADE_ITEMS] = answer
    assert (await course_grades(campus, 32338)).detalle[0].rango is None
