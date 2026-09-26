"""Minimal client for Moodle's REST web service API.

This is only the transport: it can call any function. Tools must go through
:class:`cvuex_mcp.campus.Campus`, which restricts what can be called.
"""

import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Self

import httpx

from cvuex_mcp import __version__
from cvuex_mcp.rate_limit import RateLimiter
from cvuex_mcp.sites import Site

# The campus's nginx rejects httpx's default User-Agent.
USER_AGENT = f"cvuex-mcp/{__version__}"
REQUEST_TIMEOUT_SECONDS = 30
MAX_ERROR_BYTES = 10_000  # Moodle's download errors are small JSON documents


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

    async def download(self, file_url: str, destination: Path) -> int:
        """Download a campus file to ``destination`` and return its size in bytes.

        ``file_url`` is a ``fileurl`` from the web service (``webservice/pluginfile.php``).
        The token goes in the body of a POST, never in the URL, and only to this site.
        The file is written to a temporary name and renamed at the end, so an
        interrupted download never leaves half a file.
        """
        if not file_url.startswith(f"{self.site.url}/webservice/pluginfile.php/"):
            raise ValueError(f"No es un fichero de {self.site.name}: {file_url}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=destination.parent, prefix=".descarga-")
        size = 0
        try:
            with os.fdopen(fd, "wb") as tmp:
                async with (
                    self._rate_limiter.slot(),
                    self._http.stream("POST", file_url, data={"token": self._token}) as response,
                ):
                    await _raise_for_download_error(response)
                    async for chunk in response.aiter_bytes():
                        tmp.write(chunk)
                        size += len(chunk)
            os.replace(tmp_name, destination)
            return size
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise


async def _raise_for_download_error(response: httpx.Response) -> None:
    """Moodle answers failed downloads with a JSON error (HTTP 200 for an invalid
    token, 404 for a missing file). A real JSON file has no ``errorcode``."""
    is_json = response.headers.get("content-type", "").startswith("application/json")
    length = int(response.headers.get("content-length") or 0)
    if is_json and length <= MAX_ERROR_BYTES:
        await response.aread()
        try:
            error = response.json()
        except ValueError:
            error = None
        if isinstance(error, dict) and "errorcode" in error:
            error_class = InvalidTokenError if error["errorcode"] == "invalidtoken" else MoodleError
            raise error_class(
                error["errorcode"], error.get("error", "Error desconocido de Moodle.")
            )
    response.raise_for_status()
