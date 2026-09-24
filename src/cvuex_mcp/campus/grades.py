"""The student's grades, as shown in Moodle's grade reports."""

from typing import Any

from cvuex_mcp.campus.core import Campus
from cvuex_mcp.formatting import grades_url, html_to_text, iso_datetime, module_type, module_url
from cvuex_mcp.models import Calificaciones, ItemCalificacion, NotaAsignatura
from cvuex_mcp.moodle import MoodleError

NO_GRADE = "-"  # how Moodle formats a missing grade
# Why an item doesn't count towards its category (Moodle's aggregation hints).
WEIGHT_STATUSES = {
    "novalue": "vacío: no cuenta hasta que tenga nota",
    "dropped": "descartado",
    "excluded": "excluido",
    "extra": "crédito extra",
}


class CourseGradesNotAvailableError(Exception):
    def __init__(self, course_id: int) -> None:
        super().__init__(
            f"No hay calificaciones que puedas ver en la asignatura {course_id}. "
            "Usa un id de los que da mis_asignaturas."
        )


async def grades_overview(campus: Campus) -> Calificaciones:
    """The course total of every course the student is enrolled in."""
    answer = await campus.call("gradereport_overview_get_course_grades")
    course_names = await _course_names(campus)
    return Calificaciones(
        asignaturas=[
            _course_grade(campus, grade["courseid"], grade["grade"], course_names)
            for grade in answer["grades"]
        ],
        detalle=[],
    )


async def course_grades(campus: Campus, course_id: int) -> Calificaciones:
    """Every grade item of a course the student can see, with the course total."""
    try:
        answer = await campus.call(
            "gradereport_user_get_grade_items",
            courseid=course_id,
            userid=await campus.user_id(),  # 0 means "all users" here, which needs teacher rights
        )
    except MoodleError as error:
        # What Moodle answers for a course the student isn't enrolled in.
        if error.errorcode == "nopermissions":
            raise CourseGradesNotAvailableError(course_id) from error
        raise
    items = answer["usergrades"][0]["gradeitems"] if answer["usergrades"] else []
    course_items = [item for item in items if item["itemtype"] == "course"]
    root_category = course_items[0]["iteminstance"] if course_items else None
    categories = await _category_names(campus, course_id, items, root_category)

    total = course_items[0].get("gradeformatted", NO_GRADE) if course_items else NO_GRADE
    return Calificaciones(
        asignaturas=[_course_grade(campus, course_id, total, await _course_names(campus))],
        detalle=[
            _grade_item(campus, item, categories) for item in items if item["itemtype"] != "course"
        ],
    )


async def _course_names(campus: Campus) -> dict[int, str]:
    return {course.id: course.nombre for course in await campus.courses("all")}


async def _category_names(
    campus: Campus, course_id: int, items: list[dict[str, Any]], root_category: int | None
) -> dict[int, str]:
    """Category id → name. The grade report doesn't name categories, but this function
    gives each item's category name, so a category is named if it has items of its own."""
    if not any(item["itemtype"] == "category" for item in items):
        return {}
    answer = await campus.call("core_grades_get_gradeitems", courseid=course_id)
    by_item = {int(item["id"]): item.get("category") for item in answer["gradeItems"]}
    return {
        item["categoryid"]: by_item[item["id"]]
        for item in items
        if item["categoryid"] not in (None, root_category) and by_item.get(item["id"])
    }


def _course_grade(
    campus: Campus, course_id: int, grade: str, course_names: dict[int, str]
) -> NotaAsignatura:
    return NotaAsignatura(
        asignatura=course_names.get(course_id),
        asignatura_id=course_id,
        nota=_shown(grade),
        url=grades_url(campus.site, course_id),
    )


def _grade_item(
    campus: Campus, item: dict[str, Any], categories: dict[int, str]
) -> ItemCalificacion:
    if item["itemtype"] == "category":
        category = categories.get(item["iteminstance"])
        name = f"Total de {category}" if category else "Total de la categoría"
        kind = "total de categoría"
    else:
        category = categories.get(item["categoryid"])
        name = item["itemname"] or "Sin nombre"
        kind = module_type(item["itemmodule"]) if item["itemtype"] == "mod" else "ítem manual"
    cmid = item.get("cmid")
    return ItemCalificacion(
        actividad=name,
        tipo=kind,
        categoria=category,
        nota=_shown(item.get("gradeformatted")),
        rango=_shown(item.get("rangeformatted")),
        porcentaje=_shown(item.get("percentageformatted")),
        peso=_weight(item),
        comentarios=html_to_text(item.get("feedback")) or None,
        fecha=iso_datetime(item.get("gradedategraded")),
        url=module_url(campus.site, item["itemmodule"], cmid) if cmid else None,
    )


def _shown(formatted: str | None) -> str | None:
    """A formatted value as text (it may carry icons and entities), or None if missing."""
    text = html_to_text(formatted)
    return None if text in ("", NO_GRADE) else text


def _weight(item: dict[str, Any]) -> str | None:
    weight = item.get("weightformatted")
    status = WEIGHT_STATUSES.get(item.get("status", ""))
    if weight and status:
        return f"{weight} ({status})"
    return weight or status
