"""Minimal client for Moodle's REST web service API.

This is only the transport: it can call any function. Tools must go through
:class:`cvuex_mcp.campus.Campus`, which restricts what can be called.
"""

from collections.abc import Mapping, Sequence
from typing import Any, Self

import httpx

from cvuex_mcp import __version__
from cvuex_mcp.rate_limit import RateLimiter
from cvuex_mcp.sites import Site

USER_AGENT = f"cvuex-mcp/{__version__}"
REQUEST_TIMEOUT_SECONDS = 30


class MoodleError(Exception):
    def __init__(self, errorcode: str, message: str) -> None:
        super().__init__(message)
        self.errorcode = errorcode


class InvalidTokenError(MoodleError):
    """The token has expired or been revoked: the student must log in again."""


def new_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT})


def encode_params(params: Mapping[str, Any], prefix: str = "") -> dict[str, str]:
    """Flatten nested parameters into the form fields Moodle expects.

    ``{"ids": [1, 2], "options": {"a": True}}`` becomes
    ``{"ids[0]": "1", "ids[1]": "2", "options[a]": "1"}``.
    """
    fields: dict[str, str] = {}
    for key, value in params.items():
        name = f"{prefix}[{key}]" if prefix else str(key)
        if isinstance(value, Mapping):
            fields |= encode_params(value, name)
        elif isinstance(value, Sequence) and not isinstance(value, str):
            fields |= encode_params(dict(enumerate(value)), name)
        elif isinstance(value, bool):
            fields[name] = "1" if value else "0"
        else:
            fields[name] = str(value)
    return fields


class MoodleClient:
    def __init__(
        self,
        site: Site,
        token: str,
        *,
        http: httpx.AsyncClient | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        """``http`` and ``rate_limiter`` can be shared between clients; a client
        only closes the HTTP connection pool it created itself."""
        self.site = site
        self._token = token
        self._owns_http = http is None
        self._http = http or new_http_client()
        self._rate_limiter = rate_limiter or RateLimiter()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_exc_info) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def call(self, function: str, **params: Any) -> Any:
        """Call a web service function and return its decoded JSON result."""
        form = {
            "wstoken": self._token,
            "wsfunction": function,
            "moodlewsrestformat": "json",
            **encode_params(params),
        }
        async with self._rate_limiter.slot():
            response = await self._http.post(self.site.rest_url, data=form)
        response.raise_for_status()
        result = response.json()

        # Moodle reports errors with HTTP 200 and an "exception" object.
        if isinstance(result, dict) and "exception" in result:
            errorcode = result.get("errorcode", "unknown")
            error_class = InvalidTokenError if errorcode == "invalidtoken" else MoodleError
            raise error_class(errorcode, result.get("message", "Error desconocido de Moodle."))
        return result
