"""What every area needs: allowed and cached calls, the student and their courses."""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from cvuex_mcp.cache import TTLCache
from cvuex_mcp.campus.allowlist import ALLOWED_FUNCTIONS
from cvuex_mcp.formatting import course_url
from cvuex_mcp.models import Asignatura
from cvuex_mcp.moodle import MoodleClient, encode_params
from cvuex_mcp.sites import Site

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

    @property
    def site(self) -> Site:
        return self.moodle.site

    def now(self) -> float:
        return self._clock()

    async def call(self, function: str, **params: Any) -> Any:
        """Call a Moodle function, if allowed, reusing a cached answer when possible."""
        if function not in ALLOWED_FUNCTIONS:
            raise FunctionNotAllowedError(function)
        key = (function, tuple(sorted(encode_params(params).items())))
        return await self._cache.get_or_load(
            key, ALLOWED_FUNCTIONS[function], lambda: self.moodle.call(function, **params)
        )

    async def site_info(self) -> SiteInfo:
        info = await self.call("core_webservice_get_site_info")
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
        answer = await self.call(
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
                url=course_url(self.site, course["id"]),
            )
            for course in answer["courses"]
        ]
