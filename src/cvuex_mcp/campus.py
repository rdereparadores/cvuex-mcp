"""Read-only access to the student's campus: the only way tools talk to Moodle."""

from dataclasses import dataclass
from typing import Any, Literal

from cvuex_mcp.cache import TTLCache
from cvuex_mcp.formatting import course_url
from cvuex_mcp.models import Asignatura
from cvuex_mcp.moodle import MoodleClient, encode_params

# Web service functions the server may call, with how long their answers are
# cached (seconds; 0 = never). Only read functions belong here, and never
# *_view_* ones: they log accesses and can mark activities as completed.
# The student's token can do much more (submit work, post in forums...), so
# this table is the safety net: add a function only when a tool needs it.
ALLOWED_FUNCTIONS: dict[str, float] = {
    "core_webservice_get_site_info": 3600,
    "core_course_get_enrolled_courses_by_timeline_classification": 600,
}

CourseClassification = Literal["inprogress", "past", "future", "all"]


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
    def __init__(self, moodle: MoodleClient, cache: TTLCache | None = None) -> None:
        self.moodle = moodle
        self._cache = cache or TTLCache()

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

    async def _call(self, function: str, **params: Any) -> Any:
        if function not in ALLOWED_FUNCTIONS:
            raise FunctionNotAllowedError(function)
        key = (function, tuple(sorted(encode_params(params).items())))
        return await self._cache.get_or_load(
            key, ALLOWED_FUNCTIONS[function], lambda: self.moodle.call(function, **params)
        )
