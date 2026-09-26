"""Shared test helpers: fixtures and a fake Moodle server."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlparse

import httpx

from cvuex_mcp.moodle import MoodleClient
from cvuex_mcp.rate_limit import RateLimiter
from cvuex_mcp.sites import AVUEX

FIXTURES_DIR = Path(__file__).parent / "fixtures"

COURSES = "core_course_get_enrolled_courses_by_timeline_classification"
NOW = 1790265600  # 2026-09-24 18:00, Spanish time
DAY = 24 * 60 * 60


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES_DIR / f"{name}.json").read_text(encoding="utf-8"))


DOWNLOAD_PREFIX = "/zonauex/avuex/webservice/pluginfile.php"


def campus_files(contents: list) -> dict[str, bytes]:
    """Every downloadable file of a ``core_course_get_contents`` answer, with made-up
    content, ready for ``FakeMoodle(files=...)``."""
    return {
        urlparse(content["fileurl"]).path.removeprefix(DOWNLOAD_PREFIX): (
            f"contenido de {content['filename']}".encode()
        )
        for section in contents
        for module in section["modules"]
        for content in module.get("contents") or []
        if content["type"] == "file"
    }


class FakeMoodle:
    """Answers each web service function with a canned response and records the calls.

    An answer can also be a function of the request's form fields, to answer
    differently depending on the parameters. ``files`` are served for downloads,
    by their path after ``webservice/pluginfile.php``.
    """

    def __init__(
        self,
        answers: dict[str, Any | Callable[[dict[str, str]], Any]],
        files: dict[str, bytes] | None = None,
    ) -> None:
        self.answers = answers
        self.files = files or {}
        self.calls: list[dict[str, str]] = []
        """Form fields of every request received, including ``wsfunction`` and ``wstoken``."""
        self.downloads: list[httpx.Request] = []

    def functions_called(self) -> list[str]:
        return [call["wsfunction"] for call in self.calls]

    def http_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self._handle))

    def client(self, token: str = "tok") -> MoodleClient:
        return MoodleClient(
            AVUEX, token, http=self.http_client(), rate_limiter=RateLimiter(min_interval=0)
        )

    def _handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith(DOWNLOAD_PREFIX):
            return self._download(request)
        form = dict(parse_qsl(request.content.decode()))
        self.calls.append(form)
        answer = self.answers[form["wsfunction"]]
        return httpx.Response(200, json=answer(form) if callable(answer) else answer)

    def _download(self, request: httpx.Request) -> httpx.Response:
        """Like webservice/pluginfile.php: JSON errors, 404 for missing files."""
        self.downloads.append(request)
        if dict(parse_qsl(request.content.decode())).get("token") != "tok":
            error = {"error": "Ficha (token) no válida", "errorcode": "invalidtoken"}
            return httpx.Response(200, json=error)
        content = self.files.get(request.url.path.removeprefix(DOWNLOAD_PREFIX))
        if content is None:
            error = {"error": "El archivo no se encuentra", "errorcode": "filenotfound"}
            return httpx.Response(404, json=error)
        return httpx.Response(200, content=content)


def make_pdf(pages: list[str]) -> bytes:
    """A minimal real PDF with one line of text per page ("" for a page without text).

    pypdf can read PDFs but not write text into them, so the file is built by hand:
    a catalog, the pages and a standard font (WinAnsi, so Spanish accents work).
    """
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "",  # the page tree, once the pages are known
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    kids = []
    for text in pages:
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET" if text else ""
        objects.append(
            f"<< /Length {len(stream.encode('latin-1'))} >>\nstream\n{stream}\nendstream"
        )
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {len(objects)} 0 R "
            "/Resources << /Font << /F1 3 0 R >> >> >>"
        )
        kids.append(f"{len(objects)} 0 R")
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"

    pdf, offsets = bytearray(b"%PDF-1.4\n"), []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    pdf += "".join(f"{offset:010d} 00000 n \n" for offset in offsets).encode()
    pdf += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode()
    pdf += f"startxref\n{xref}\n%%EOF\n".encode()
    return bytes(pdf)
