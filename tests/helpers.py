"""Shared test helpers: fixtures and a fake Moodle server."""

import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl

import httpx

from cvuex_mcp.moodle import MoodleClient
from cvuex_mcp.rate_limit import RateLimiter
from cvuex_mcp.sites import AVUEX

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES_DIR / f"{name}.json").read_text(encoding="utf-8"))


class FakeMoodle:
    """Answers each web service function with a canned response and records the calls."""

    def __init__(self, answers: dict[str, Any]) -> None:
        self.answers = answers
        self.calls: list[dict[str, str]] = []
        """Form fields of every request received, including ``wsfunction`` and ``wstoken``."""

    def functions_called(self) -> list[str]:
        return [call["wsfunction"] for call in self.calls]

    def http_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self._handle))

    def client(self, token: str = "tok") -> MoodleClient:
        return MoodleClient(
            AVUEX, token, http=self.http_client(), rate_limiter=RateLimiter(min_interval=0)
        )

    def _handle(self, request: httpx.Request) -> httpx.Response:
        form = dict(parse_qsl(request.content.decode()))
        self.calls.append(form)
        return httpx.Response(200, json=self.answers[form["wsfunction"]])
