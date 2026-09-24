"""Submission status of the student's assignments."""

from typing import Any

from cvuex_mcp.campus.core import Campus
from cvuex_mcp.formatting import html_to_text, iso_datetime, module_url
from cvuex_mcp.models import EstadoEntrega, ListaEntregas, SubmissionState
from cvuex_mcp.moodle import InvalidTokenError, MoodleError

MAX_ASSIGNMENTS = 30  # each one needs its own request

SUBMISSION_STATES: dict[str, SubmissionState] = {
    "new": "sin_entregar",
    "draft": "borrador",
    "submitted": "entregada",
    "reopened": "reabierta",
}
PENDING_STATES = {"sin_entregar", "borrador", "reabierta"}


async def submission_statuses(
    campus: Campus, course_id: int | None = None, *, only_pending: bool = True
) -> ListaEntregas:
    """Submission status of the student's assignments, by due date.

    Without a course, it looks at the courses in progress. Each assignment
    needs its own request, so at most ``MAX_ASSIGNMENTS`` are checked: those
    whose due date is closest to now.
    """
    if course_id is not None:
        course_ids = [course_id]
    else:
        course_ids = [course.id for course in await campus.courses("inprogress")]
    if not course_ids:
        return ListaEntregas(entregas=[], avisos=[])

    answer = await campus.call("mod_assign_get_assignments", courseids=course_ids)
    now = campus.now()
    assignments = [(course, a) for course in answer["courses"] for a in course["assignments"]]
    assignments.sort(key=lambda pair: distance_to_due_date(pair[1], now))

    warnings = []
    if len(assignments) > MAX_ASSIGNMENTS:
        warnings.append(
            f"Hay {len(assignments)} tareas; solo se han consultado las {MAX_ASSIGNMENTS} "
            "con fecha límite más cercana. Filtra por asignatura para ver el resto."
        )
        assignments = assignments[:MAX_ASSIGNMENTS]

    found: list[tuple[float, EstadoEntrega]] = []
    for course, assignment in assignments:
        try:
            status = await campus.call(
                "mod_assign_get_submission_status", assignid=assignment["id"]
            )
        except InvalidTokenError:
            raise
        except MoodleError as error:
            warnings.append(f"No se pudo consultar '{assignment['name']}': {error}")
            continue
        submission = _submission(campus, course, assignment, status, now)
        if not only_pending or submission.estado in PENDING_STATES:
            due = _due_date(assignment, status)
            found.append((due or float("inf"), submission))

    found.sort(key=lambda pair: pair[0])
    return ListaEntregas(entregas=[submission for _, submission in found], avisos=warnings)


def distance_to_due_date(assignment: dict[str, Any], now: float) -> float:
    """Seconds between now and the due date; assignments without one go last."""
    return abs(assignment["duedate"] - now) if assignment["duedate"] else float("inf")


def _submission(
    campus: Campus,
    course: dict[str, Any],
    assignment: dict[str, Any],
    status: dict[str, Any],
    now: float,
) -> EstadoEntrega:
    attempt = status.get("lastattempt") or {}
    # In group assignments the group's submission is the one that counts.
    submission = attempt.get("teamsubmission" if assignment["teamsubmission"] else "submission")
    if assignment["nosubmissions"]:
        state: SubmissionState = "sin_entrega_online"
    else:
        state = SUBMISSION_STATES.get((submission or {}).get("status"), "sin_entregar")
    due = _due_date(assignment, status)
    feedback = status.get("feedback") or {}
    return EstadoEntrega(
        tarea=assignment["name"],
        asignatura=course["fullname"],
        asignatura_id=course["id"],
        fecha_limite=iso_datetime(due),
        vencida=bool(due) and due < now,
        estado=state,
        puede_entregar=bool(attempt.get("canedit")),
        calificacion=html_to_text(feedback.get("gradefordisplay")) or None,
        comentarios_profesor=_feedback_comments(feedback),
        url=module_url(campus.site, "assign", assignment["cmid"]),
    )


def _due_date(assignment: dict[str, Any], status: dict[str, Any]) -> int:
    """The student's own due date: an extension, if granted, replaces the general one."""
    extension = (status.get("lastattempt") or {}).get("extensionduedate")
    return extension or assignment["duedate"]


def _feedback_comments(feedback: dict[str, Any]) -> str | None:
    texts = [
        html_to_text(field["text"])
        for plugin in feedback.get("plugins", [])
        if plugin["type"] == "comments"
        for field in plugin.get("editorfields", [])
    ]
    return "\n\n".join(text for text in texts if text) or None
