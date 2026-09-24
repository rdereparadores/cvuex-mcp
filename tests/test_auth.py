import base64
import hashlib
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from cvuex_mcp.auth import LoginError, login_with_browser, parse_token_url
from cvuex_mcp.credentials import Credentials
from cvuex_mcp.sites import Site

SITE = Site(key="test", name="Test", url="https://moodle.example/test")
PASSPORT = "abc123"


def token_url(site: Site, passport: str, *parts: str) -> str:
    site_id = hashlib.md5((site.url + passport).encode()).hexdigest()
    payload = ":::".join((site_id, *parts))
    return "moodlemobile://token=" + base64.b64encode(payload.encode()).decode()


class TestParseTokenUrl:
    def test_with_private_token(self):
        url = token_url(SITE, PASSPORT, "tok", "priv")
        assert parse_token_url(url, site=SITE, passport=PASSPORT) == Credentials("tok", "priv")

    def test_without_private_token(self):
        url = token_url(SITE, PASSPORT, "tok")
        assert parse_token_url(url, site=SITE, passport=PASSPORT) == Credentials("tok", None)

    def test_rejects_other_passport(self):
        url = token_url(SITE, "someone-else", "tok")
        with pytest.raises(LoginError, match="no corresponde"):
            parse_token_url(url, site=SITE, passport=PASSPORT)

    @pytest.mark.parametrize(
        "url",
        [
            "https://moodle.example/",
            "moodlemobile://token=not base64!",
            "moodlemobile://token=" + base64.b64encode(b"no-separators").decode(),
        ],
    )
    def test_rejects_malformed(self, url):
        with pytest.raises(LoginError):
            parse_token_url(url, site=SITE, passport=PASSPORT)


@pytest.fixture
def fake_moodle() -> Iterator[Site]:
    """Local server imitating Moodle's SSO: launch.php → login page → token redirect."""
    site_holder: list[Site] = []

    class Handler(BaseHTTPRequestHandler):
        passport = ""

        def do_GET(self):
            url = urlparse(self.path)
            if url.path.endswith("/admin/tool/mobile/launch.php"):
                Handler.passport = parse_qs(url.query)["passport"][0]
                self.redirect("/login")
            elif url.path == "/login":
                # Stands in for the CAS/Microsoft form the student fills in.
                body = b"<script>setTimeout(() => location = '/done', 200)</script>"
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(body)
            elif url.path == "/done":
                self.redirect(token_url(site_holder[0], Handler.passport, "tok", "priv"))
            else:
                self.send_error(404)

        def redirect(self, location: str) -> None:
            self.send_response(303)
            self.send_header("Location", location)
            self.end_headers()

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    site_holder.append(Site(key="test", name="Test", url=f"http://127.0.0.1:{server.server_port}"))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield site_holder[0]
    server.shutdown()


@pytest.mark.browser
async def test_login_captures_token_redirect(fake_moodle):
    credentials = await login_with_browser(fake_moodle, headless=True, timeout=15)
    assert credentials == Credentials("tok", "priv")
