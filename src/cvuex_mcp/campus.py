"""Read-only access to the student's campus: the only way tools talk to Moodle."""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from cvuex_mcp.cache import TTLCache
from cvuex_mcp.formatting import (
    course_url,
    describe_change,
    html_to_text,
    iso_datetime,
    module_type,
    module_url,
)
from cvuex_mcp.models import (
    Asignatura,
    EstadoEntrega,
    ListaEntregas,
    ListaNovedades,
    ListaPlazos,
    Novedad,
    NovedadesAsignatura,
    Plazo,
    SubmissionState,
)
from cvuex_mcp.moodle import InvalidTokenError, MoodleClient, MoodleError, encode_params

# Web service functions the server may call, with how long their answers are
# cached (seconds; 0 = never). Only read functions belong here, and never
# *_view_* ones: they log accesses and can mark activities as completed.
# The student's token can do much more (submit work, post in forums...), so
# this table is the safety net: add a function only when a tool needs it.
ALLOWED_FUNCTIONS: dict[str, float] = {
    "core_webservice_get_site_info": 3600,
    "core_course_get_enrolled_courses_by_timeline_classification": 600,
    "core_calendar_get_action_events_by_timesort": 120,
    "core_calendar_get_action_events_by_course": 120,
    "mod_assign_get_assignments": 300,
    "mod_assign_get_submission_status": 120,
    "core_course_get_updates_since": 0,
    "core_course_get_contents": 600,
}

CourseClassification = Literal["inprogress", "past", "future", "all"]

DAY_SECONDS = 24 * 60 * 60
OVERDUE_LOOKBACK_DAYS = 30
MAX_EVENTS = 50  # the most Moodle returns per request
MAX_ASSIGNMENTS = 30  # each one needs its own request

SUBMISSION_STATES: dict[str, SubmissionState] = {
    "new": "sin_entregar",
    "draft": "borrador",
    "submitted": "entregada",
    "reopened": "reabierta",
}
PENDING_STATES = {"sin_entregar", "borrador", "reabierta"}


def distance_to_due_date(assignment: dict[str, Any], now: float) -> float:
    """Seconds between now and the due date; assignments without one go last."""
    return abs(assignment["duedate"] - now) if assignment["duedate"] else float("inf")


class FunctionNotAllowedError(Exception):
    def __init__(self, function: str) -> None:
        super().__init__(f"La función '{function}' no está permitida en este servidor.")


@dataclass(frozen=True)
class SiteInfo:
    site_name: str
    user_id: int
    username: str
    full_name: str
    moodle_release: str
    functions: tuple[str, ...]
    """Web service functions the token is allowed to call on the server side."""


class Campus:
    def __init__(
        self,
        moodle: MoodleClient,
        cache: TTLCache | None = None,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.moodle = moodle
        self._cache = cache or TTLCache()
        self._clock = clock

    async def site_info(self) -> SiteInfo:
        info = await self._call("core_webservice_get_site_info")
        return SiteInfo(
            site_name=info["sitename"],
            user_id=info["userid"],
            username=info["username"],
            full_name=info["fullname"],
            moodle_release=info.get("release", ""),
            functions=tuple(sorted(f["name"] for f in info.get("functions", []))),
        )

    async def user_id(self) -> int:
        """Needed by several functions; cached along with the site info."""
        return (await self.site_info()).user_id

    async def courses(self, classification: CourseClassification) -> list[Asignatura]:
        """Courses the student is enrolled in, as grouped on the Moodle dashboard."""
        answer = await self._call(
            "core_course_get_enrolled_courses_by_timeline_classification",
            classification=classification,
        )
        return [
            Asignatura(
                id=course["id"],
                nombre=course["fullname"],
                titulacion=course.get("coursecategory", ""),
                # Moodle sends progress 0 even when it doesn't track completion.
                progreso=round(course["progress"]) if course.get("hasprogress") else None,
                url=course_url(self.moodle.site, course["id"]),
            )
            for course in answer["courses"]
        ]

    async def deadlines(self, days: int, course_id: int | None = None) -> ListaPlazos:
        """Dated activities still waiting for the student (submit, attempt...), by date.

        Moodle only returns events that still need an action, so overdue ones
        from the last ``OVERDUE_LOOKBACK_DAYS`` are included: they are still pending.
        """
        # Minute precision keeps the cache key stable between close calls.
        now = int(self._clock()) // 60 * 60
        window = {
            "timesortfrom": now - OVERDUE_LOOKBACK_DAYS * DAY_SECONDS,
            "timesortto": now + days * DAY_SECONDS,
            "limitnum": MAX_EVENTS,
        }
        if course_id is None:
            answer = await self._call("core_calendar_get_action_events_by_timesort", **window)
        else:
            answer = await self._call(
                "core_calendar_get_action_events_by_course", courseid=course_id, **window
            )
        return ListaPlazos(
            desde=iso_datetime(window["timesortfrom"]),
            hasta=iso_datetime(window["timesortto"]),
            plazos=[self._deadline(event, now) for event in answer["events"]],
        )

    @staticmethod
    def _deadline(event: dict[str, Any], now: int) -> Plazo:
        course = event.get("course") or {}
        action = event.get("action") or {}
        return Plazo(
            fecha=iso_datetime(event["timesort"]),
            asignatura=course.get("fullname"),
            asignatura_id=course.get("id"),
            actividad=event.get("activityname") or event["name"],
            tipo=module_type(event.get("modulename")),
            evento=event["name"],
            accion=action.get("name") if action.get("actionable") else None,
            vencido=event["timesort"] < now,
            url=event["url"],
        )

    async def submissions(
        self, course_id: int | None = None, *, only_pending: bool = True
    ) -> ListaEntregas:
        """Submission status of the student's assignments, by due date.

        Without a course, it looks at the courses in progress. Each assignment
        needs its own request, so at most ``MAX_ASSIGNMENTS`` are checked: those
        whose due date is closest to now.
        """
        if course_id is not None:
            course_ids = [course_id]
        else:
            course_ids = [course.id for course in await self.courses("inprogress")]
        if not course_ids:
            return ListaEntregas(entregas=[], avisos=[])

        answer = await self._call("mod_assign_get_assignments", courseids=course_ids)
        now = self._clock()
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
                status = await self._call(
                    "mod_assign_get_submission_status", assignid=assignment["id"]
                )
            except InvalidTokenError:
                raise
            except MoodleError as error:
                warnings.append(f"No se pudo consultar '{assignment['name']}': {error}")
                continue
            submission = self._submission(course, assignment, status, now)
            if not only_pending or submission.estado in PENDING_STATES:
                due = self._due_date(assignment, status)
                found.append((due or float("inf"), submission))

        found.sort(key=lambda pair: pair[0])
        return ListaEntregas(entregas=[submission for _, submission in found], avisos=warnings)

    def _submission(
        self, course: dict[str, Any], assignment: dict[str, Any], status: dict[str, Any], now: float
    ) -> EstadoEntrega:
        attempt = status.get("lastattempt") or {}
        # In group assignments the group's submission is the one that counts.
        submission = attempt.get("teamsubmission" if assignment["teamsubmission"] else "submission")
        if assignment["nosubmissions"]:
            state: SubmissionState = "sin_entrega_online"
        else:
            state = SUBMISSION_STATES.get((submission or {}).get("status"), "sin_entregar")
        due = self._due_date(assignment, status)
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
            comentarios_profesor=self._feedback_comments(feedback),
            url=module_url(self.moodle.site, "assign", assignment["cmid"]),
        )

    @staticmethod
    def _due_date(assignment: dict[str, Any], status: dict[str, Any]) -> int:
        """The student's own due date: an extension, if granted, replaces the general one."""
        extension = (status.get("lastattempt") or {}).get("extensionduedate")
        return extension or assignment["duedate"]

    @staticmethod
    def _feedback_comments(feedback: dict[str, Any]) -> str | None:
        texts = [
            html_to_text(field["text"])
            for plugin in feedback.get("plugins", [])
            if plugin["type"] == "comments"
            for field in plugin.get("editorfields", [])
        ]
        return "\n\n".join(text for text in texts if text) or None

    async def changes(self, since: int, course_id: int | None = None) -> ListaNovedades:
        """What changed in the courses in progress (or in one course) since a moment."""
        if course_id is None:
            courses = await self.courses("inprogress")
        else:
            courses = [course for course in await self.courses("all") if course.id == course_id]

        with_changes = []
        for course in courses:
            answer = await self._call(
                "core_course_get_updates_since", courseid=course.id, since=since
            )
            instances = [
                instance
                for instance in answer["instances"]
                if instance["contextlevel"] == "module" and instance["updates"]
            ]
            if instances:
                modules = await self._course_modules(course.id)
                news = [self._change(instance, modules, course) for instance in instances]
                with_changes.append(
                    NovedadesAsignatura(
                        asignatura=course.nombre, asignatura_id=course.id, novedades=news
                    )
                )
        return ListaNovedades(desde=iso_datetime(since), asignaturas=with_changes)

    async def _course_modules(self, course_id: int) -> dict[int, dict[str, Any]]:
        """The course's activities and resources visible to the student, by course module id."""
        sections = await self._call("core_course_get_contents", courseid=course_id)
        return {module["id"]: module for section in sections for module in section["modules"]}

    def _change(
        self, instance: dict[str, Any], modules: dict[int, dict[str, Any]], course: Asignatura
    ) -> Novedad:
        updates = instance["updates"]
        dates = [update["timeupdated"] for update in updates if update.get("timeupdated")]
        changes = [describe_change(u["name"], len(u.get("itemids") or [])) for u in updates]
        module = modules.get(instance["id"])
        if module:
            name = module["name"]
            kind = module_type(module["modname"])
            url = module_url(self.moodle.site, module["modname"], instance["id"])
        else:  # e.g. an activity hidden from students
            name, kind, url = f"Actividad {instance['id']} (no visible)", "otro", course.url
        return Novedad(
            actividad=name,
            tipo=kind,
            cambios=changes,
            fecha=iso_datetime(max(dates, default=None)),
            url=url,
        )

    async def _call(self, function: str, **params: Any) -> Any:
        if function not in ALLOWED_FUNCTIONS:
            raise FunctionNotAllowedError(function)
        key = (function, tuple(sorted(encode_params(params).items())))
        return await self._cache.get_or_load(
            key, ALLOWED_FUNCTIONS[function], lambda: self.moodle.call(function, **params)
        )
