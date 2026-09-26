"""The teachers of each course: those Moodle shows as its contacts, with their profile.

Only the contacts' ids are ever looked up, never an id from outside, so no other
participant of the course (e.g. a classmate) can be asked for.
"""

from typing import Any

from cvuex_mcp.campus.core import Campus
from cvuex_mcp.formatting import html_to_text, profile_url, truncate
from cvuex_mcp.models import Asignatura, ListaProfesorado, Profesor, ProfesoradoAsignatura

MAX_PROFILE_CHARS = 1000


async def course_teachers(campus: Campus, course_id: int | None) -> ListaProfesorado:
    """The teachers of the course ``course_id``, or of those in progress if None."""
    courses = await campus.enrolled_courses(course_id)
    answer = await campus.call(
        "core_course_get_courses_by_field",
        field="ids",
        value=",".join(str(course.id) for course in courses),
    )
    contacts = {course["id"]: course.get("contacts", []) for course in answer["courses"]}
    profiles = await _profiles(campus, {c["id"] for cs in contacts.values() for c in cs})
    return ListaProfesorado(
        asignaturas=[
            _course_teachers(campus, course, contacts.get(course.id, []), profiles)
            for course in courses
        ]
    )


async def _profiles(campus: Campus, user_ids: set[int]) -> dict[int, dict[str, Any]]:
    """Profiles by id. Moodle leaves out those the student cannot see."""
    if not user_ids:
        return {}
    users = await campus.call("core_user_get_users_by_field", field="id", values=sorted(user_ids))
    return {user["id"]: user for user in users}


def _course_teachers(
    campus: Campus,
    course: Asignatura,
    contacts: list[dict[str, Any]],
    profiles: dict[int, dict[str, Any]],
) -> ProfesoradoAsignatura:
    return ProfesoradoAsignatura(
        asignatura=course.nombre,
        asignatura_id=course.id,
        profesores=[
            _teacher(campus, course.id, contact, profiles.get(contact["id"], {}))
            for contact in contacts
        ],
    )


def _teacher(
    campus: Campus, course_id: int, contact: dict[str, Any], profile: dict[str, Any]
) -> Profesor:
    description = html_to_text(profile.get("description"))
    return Profesor(
        nombre=contact["fullname"],
        correo=profile.get("email") or None,
        perfil=truncate(description, MAX_PROFILE_CHARS) or None,
        url=profile_url(campus.site, contact["id"], course_id),
    )
