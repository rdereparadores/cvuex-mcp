import pytest
from helpers import COURSES, FakeMoodle, load_fixture

from cvuex_mcp.campus import Campus, CourseNotEnrolledError
from cvuex_mcp.campus.teachers import course_teachers

COURSES_BY_FIELD = "core_course_get_courses_by_field"
USERS = "core_user_get_users_by_field"
URL = "https://campusvirtual.unex.es/zonauex/avuex"


def campus_with_teachers(users: list | None = None) -> tuple[Campus, FakeMoodle]:
    """The real contacts of 32338 (two) and 32368 (one); the descriptions are made up."""
    fake = FakeMoodle(
        {
            COURSES: load_fixture(COURSES),
            COURSES_BY_FIELD: load_fixture(COURSES_BY_FIELD),
            USERS: load_fixture(USERS) if users is None else users,
        }
    )
    return Campus(fake.client()), fake


def requests(fake: FakeMoodle, function: str) -> list[dict]:
    return [call for call in fake.calls if call["wsfunction"] == function]


async def test_teachers_of_a_course():
    campus, fake = campus_with_teachers()
    [course] = (await course_teachers(campus, 32338)).asignaturas

    assert (course.asignatura, course.asignatura_id) == (
        "APRENDIZAJE AUTOMÁTICO Y APRENDIZAJE PROFUNDO",
        32338,
    )
    assert [teacher.model_dump() for teacher in course.profesores] == [
        {
            "nombre": "Persona 1",
            "correo": "persona1@example.com",
            "perfil": "Tutorías: martes y miércoles de 10:00 a 12:00.\n\n"
            "Despacho 1.23, edificio de Informática.",
            "url": f"{URL}/user/view.php?id=1001&course=32338",
        },
        {
            "nombre": "Persona 2",
            "correo": "persona2@example.com",
            "perfil": None,  # an empty profile
            "url": f"{URL}/user/view.php?id=1002&course=32338",
        },
    ]
    [request] = requests(fake, COURSES_BY_FIELD)
    assert (request["field"], request["value"]) == ("ids", "32338")


async def test_only_the_contacts_profiles_are_asked_for():
    campus, fake = campus_with_teachers()
    await course_teachers(campus, None)

    [request] = requests(fake, COURSES_BY_FIELD)
    assert request["value"] == "32338,32337,32327"  # the courses in progress
    [request] = requests(fake, USERS)
    asked = [value for key, value in request.items() if key.startswith("values[")]
    assert (request["field"], asked) == ("id", ["1001", "1002", "1003"])


async def test_courses_without_contacts_have_no_teachers():
    campus, _ = campus_with_teachers()
    result = await course_teachers(campus, None)
    teachers = {course.asignatura_id: len(course.profesores) for course in result.asignaturas}
    assert teachers == {32338: 2, 32337: 0, 32327: 0}


async def test_a_profile_the_student_cannot_see():
    """Moodle leaves out the profiles, and the emails, the student is not allowed to see."""
    users = load_fixture(USERS)
    del users[0]["email"]
    campus, _ = campus_with_teachers(users[:1])
    [course] = (await course_teachers(campus, 32338)).asignaturas

    assert [(t.nombre, t.correo) for t in course.profesores] == [
        ("Persona 1", None),
        ("Persona 2", None),
    ]
    assert course.profesores[1].perfil is None


async def test_no_profiles_are_asked_for_without_contacts():
    campus, fake = campus_with_teachers()
    fake.answers[COURSES_BY_FIELD] = {"courses": [], "warnings": []}
    [course] = (await course_teachers(campus, 32338)).asignaturas
    assert course.profesores == []
    assert requests(fake, USERS) == []


async def test_a_course_not_enrolled_in():
    campus, fake = campus_with_teachers()
    with pytest.raises(CourseNotEnrolledError):
        await course_teachers(campus, 32000)
    assert requests(fake, COURSES_BY_FIELD) == []
