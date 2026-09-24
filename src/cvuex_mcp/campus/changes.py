"""What changed in the student's courses."""

from typing import Any

from cvuex_mcp.campus.core import Campus
from cvuex_mcp.formatting import describe_change, iso_datetime, module_type, module_url
from cvuex_mcp.models import Asignatura, ListaNovedades, Novedad, NovedadesAsignatura


async def course_changes(
    campus: Campus, since: int, course_id: int | None = None
) -> ListaNovedades:
    """What changed in the courses in progress (or in one course) since a moment."""
    if course_id is None:
        courses = await campus.courses("inprogress")
    else:
        courses = [course for course in await campus.courses("all") if course.id == course_id]

    with_changes = []
    for course in courses:
        answer = await campus.call("core_course_get_updates_since", courseid=course.id, since=since)
        instances = [
            instance
            for instance in answer["instances"]
            if instance["contextlevel"] == "module" and instance["updates"]
        ]
        if instances:
            modules = await course_modules(campus, course.id)
            news = [_change(campus, instance, modules, course) for instance in instances]
            with_changes.append(
                NovedadesAsignatura(
                    asignatura=course.nombre, asignatura_id=course.id, novedades=news
                )
            )
    return ListaNovedades(desde=iso_datetime(since), asignaturas=with_changes)


async def course_modules(campus: Campus, course_id: int) -> dict[int, dict[str, Any]]:
    """The course's activities and resources visible to the student, by course module id."""
    sections = await campus.call("core_course_get_contents", courseid=course_id)
    return {module["id"]: module for section in sections for module in section["modules"]}


def _change(
    campus: Campus,
    instance: dict[str, Any],
    modules: dict[int, dict[str, Any]],
    course: Asignatura,
) -> Novedad:
    updates = instance["updates"]
    dates = [update["timeupdated"] for update in updates if update.get("timeupdated")]
    changes = [describe_change(u["name"], len(u.get("itemids") or [])) for u in updates]
    module = modules.get(instance["id"])
    if module:
        name = module["name"]
        kind = module_type(module["modname"])
        url = module_url(campus.site, module["modname"], instance["id"])
    else:  # e.g. an activity hidden from students
        name, kind, url = f"Actividad {instance['id']} (no visible)", "otro", course.url
    return Novedad(
        actividad=name,
        tipo=kind,
        cambios=changes,
        fecha=iso_datetime(max(dates, default=None)),
        url=url,
    )
