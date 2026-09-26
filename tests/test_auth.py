import base64
import hashlib
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from playwright.async_api import Error as PlaywrightError

from cvuex_mcp import auth
from cvuex_mcp.auth import LoginError, launch_browser, login_with_browser, parse_token_url
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


class FakeChromium:
    """Playwright's ``chromium`` with some of the student's browsers installed."""

    def __init__(self, channels: set[str], executable_path: Path) -> None:
        self.channels = channels
        self.executable_path = str(executable_path)
        self.launched: list[str | None] = []

    async def launch(self, *, channel: str | None = None, headless: bool) -> str:
        self.launched.append(channel)
        if channel is not None and channel not in self.channels:
            raise PlaywrightError(f"Chromium distribution '{channel}' is not found")
        return channel or "chromium"


class FakePlaywright:
    def __init__(self, chromium: FakeChromium) -> None:
        self.chromium = chromium


@pytest.fixture
def downloads(monkeypatch, tmp_path) -> list[Path]:
    """Stands in for downloading Chromium, which creates its executable."""
    done: list[Path] = []

    async def install() -> None:
        path = tmp_path / "chromium"
        path.touch()
        done.append(path)

    monkeypatch.setattr(auth, "install_chromium", install)
    return done


async def launch(channels: set[str], executable: Path) -> tuple[str, FakeChromium, list[str]]:
    chromium = FakeChromium(channels, executable)
    messages: list[str] = []
    browser = await launch_browser(FakePlaywright(chromium), headless=True, notify=messages.append)
    return browser, chromium, messages


async def test_the_students_chrome_comes_first(tmp_path, downloads):
    browser, chromium, _ = await launch({"chrome", "msedge"}, tmp_path / "chromium")
    assert (browser, chromium.launched, downloads) == ("chrome", ["chrome"], [])


async def test_then_edge(tmp_path, downloads):
    browser, chromium, _ = await launch({"msedge"}, tmp_path / "chromium")
    assert (browser, chromium.launched, downloads) == ("msedge", ["chrome", "msedge"], [])


async def test_then_chromium_if_already_downloaded(tmp_path, downloads):
    (tmp_path / "chromium").touch()
    browser, _, messages = await launch(set(), tmp_path / "chromium")
    assert (browser, downloads, messages) == ("chromium", [], [])


async def test_chromium_is_downloaded_the_first_time(tmp_path, downloads):
    browser, _, messages = await launch(set(), tmp_path / "chromium")
    assert (browser, downloads) == ("chromium", [tmp_path / "chromium"])
    [message] = messages
    assert "se descargará un navegador" in message


async def test_a_failed_download_suggests_installing_chrome(monkeypatch):
    class FailedProcess:
        async def wait(self) -> int:
            return 1

    commands = []

    async def run(*command):
        commands.append(command[1:])
        return FailedProcess()

    monkeypatch.setattr(auth.asyncio, "create_subprocess_exec", run)
    with pytest.raises(LoginError, match="Instala Google Chrome o Microsoft Edge"):
        await auth.install_chromium()
    # Only the browser the login shows, not Playwright's separate headless one.
    assert commands == [("-m", "playwright", "install", "--no-shell", "chromium")]
