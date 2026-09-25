"""What a course contains: its sections, activities, resources and files."""

from typing import Any

from cvuex_mcp.campus.core import Campus
from cvuex_mcp.formatting import (
    course_url,
    html_to_text,
    human_size,
    iso_datetime,
    module_type,
    short_text,
)
from cvuex_mcp.models import ContenidoAsignatura, ElementoCurso, Fichero, SeccionCurso
from cvuex_mcp.moodle import MoodleError

MAX_FILES_PER_ITEM = 50  # a folder can hold hundreds
SUMMARY_CHARS = 500
SUBSECTION = "subsection"  # Moodle 5 modules that hold a section of their own


class CourseNotAvailableError(Exception):
    def __init__(self, course_id: int) -> None:
        super().__init__(
            f"No se pudo abrir la asignatura {course_id}: no existe o no estás matriculado. "
            "Usa un id de los que da mis_asignaturas."
        )


async def course_contents(
    campus: Campus, course_id: int, section: int | None = None
) -> ContenidoAsignatura:
    """The course as its main page shows it to the student.

    With ``section``, only that section and the subsections inside it.
    """
    try:
        sections = await campus.call("core_course_get_contents", courseid=course_id)
    except MoodleError as error:
        # Real answers for a course that doesn't exist and for one the student isn't in.
        if error.errorcode in ("invalidrecordunknown", "errorcoursecontextnotvalid"):
            raise CourseNotAvailableError(course_id) from error
        raise

    parents = _subsection_parents(sections)
    if section is not None:
        sections = [
            s
            for s in sections
            if s["section"] == section or parents.get(s["id"], {}).get("section") == section
        ]
    warnings: list[str] = []
    course_names = {course.id: course.nombre for course in await campus.courses("all")}
    return ContenidoAsignatura(
        asignatura=course_names.get(course_id),
        asignatura_id=course_id,
        url=course_url(campus.site, course_id),
        secciones=[_section(s, parents, warnings) for s in sections],
        avisos=warnings,
    )


def _subsection_parents(sections: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """Subsection id → the section that contains it.

    A subsection is listed as a section of its own (``component`` mod_subsection,
    ``itemid`` the module's instance) and as a module inside its parent.
    """
    parent_of_instance = {
        module["instance"]: parent
        for parent in sections
        for module in parent["modules"]
        if module["modname"] == SUBSECTION
    }
    return {
        s["id"]: parent_of_instance[s["itemid"]]
        for s in sections
        if s.get("component") == "mod_subsection" and s.get("itemid") in parent_of_instance
    }


def _section(
    section: dict[str, Any], parents: dict[int, dict[str, Any]], warnings: list[str]
) -> SeccionCurso:
    parent = parents.get(section["id"])
    return SeccionCurso(
        numero=section["section"],
        nombre=section["name"],
        dentro_de=parent["name"] if parent else None,
        resumen=short_text(section.get("summary"), SUMMARY_CHARS),
        disponible=section.get("uservisible", True),
        restriccion=html_to_text(section.get("availabilityinfo")) or None,
        elementos=[
            _item(module, warnings)
            for module in section["modules"]
            if module["modname"] != SUBSECTION  # shown as a section
        ],
    )


def _item(module: dict[str, Any], warnings: list[str]) -> ElementoCurso:
    contents = module.get("contents") or []
    completion = module.get("completiondata") or {}
    return ElementoCurso(
        nombre=module["name"],
        tipo=module_type(module["modname"]),
        disponible=module.get("uservisible", True),
        restriccion=html_to_text(module.get("availabilityinfo")) or None,
        descripcion=short_text(module.get("description"), SUMMARY_CHARS),
        fechas=[
            f"{date['label']} {iso_datetime(date['timestamp'])}"
            for date in module.get("dates", [])
            if date.get("timestamp")
        ],
        completado=completion.get("isoverallcomplete") if completion.get("hascompletion") else None,
        ficheros=_files(module, contents, warnings),
        apartados=[
            c["content"] for c in contents if module["modname"] == "book" and _is_chapter(c)
        ],
        enlace=next((c["fileurl"] for c in contents if c["type"] == "url"), None),
        url=module.get("url"),
    )


def _files(
    module: dict[str, Any], contents: list[dict[str, Any]], warnings: list[str]
) -> list[Fichero]:
    """The files the student would download: not the text of pages and books,
    which Moodle also sends as files (index.html)."""
    if module["modname"] in ("page", "book", "url"):
        return []
    files = [c for c in contents if c["type"] == "file"]
    if len(files) > MAX_FILES_PER_ITEM:
        warnings.append(
            f"'{module['name']}' tiene {len(files)} ficheros; solo se muestran "
            f"{MAX_FILES_PER_ITEM}."
        )
    return [
        Fichero(
            nombre=(f["filepath"] or "/").lstrip("/") + f["filename"],
            tamano=human_size(f.get("filesize")),
            fecha=iso_datetime(f.get("timemodified")),
        )
        for f in files[:MAX_FILES_PER_ITEM]
    ]


def _is_chapter(content: dict[str, Any]) -> bool:
    """Each book chapter is an index.html file in its own folder, titled in ``content``."""
    return content["type"] == "file" and content["filename"] == "index.html"
