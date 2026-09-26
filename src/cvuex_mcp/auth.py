"""SSO login through the UEx CAS, the same way the official Moodle app does it.

1. A real browser opens ``launch.php`` with a random ``passport``: the student's
   Chrome or Edge if installed, or else Playwright's Chromium, downloaded the first
   time. Either way with a fresh profile, so none of the student's cookies are used.
2. The student logs in themselves (CAS → Microsoft, including MFA).
   The password never passes through this program.
3. Moodle answers with a redirect to
   ``moodlemobile://token=base64(md5(wwwroot + passport):::token[:::private_token])``,
   which is captured here instead of opening the app.
"""

import asyncio
import base64
import binascii
import hashlib
import hmac
import secrets
import sys
from collections.abc import Callable
from pathlib import Path

from playwright.async_api import Browser, Playwright, Response, async_playwright
from playwright.async_api import Error as PlaywrightError

from cvuex_mcp.credentials import Credentials
from cvuex_mcp.sites import Site

SERVICE = "moodle_mobile_app"
URL_SCHEME = "moodlemobile"
TOKEN_URL_PREFIX = f"{URL_SCHEME}://token="
LOGIN_TIMEOUT_SECONDS = 300
INSTALLED_BROWSERS = ("chrome", "msedge")
"""Playwright channels of the browsers the student may already have, in order."""


class LoginError(Exception):
    pass


def parse_token_url(url: str, *, site: Site, passport: str) -> Credentials:
    """Extract the credentials from Moodle's ``moodlemobile://token=...`` redirect.

    The embedded site id proves the answer belongs to this login attempt.
    """
    if not url.startswith(TOKEN_URL_PREFIX):
        raise LoginError("La respuesta de Moodle no contiene un token.")

    try:
        decoded = base64.b64decode(url.removeprefix(TOKEN_URL_PREFIX), validate=True).decode()
    except (binascii.Error, UnicodeDecodeError):
        raise LoginError("El token recibido de Moodle no es válido.") from None

    parts = decoded.split(":::")
    if len(parts) not in (2, 3):
        raise LoginError("El token recibido de Moodle tiene un formato inesperado.")
    site_id, token, *private = parts

    expected_site_id = hashlib.md5((site.url + passport).encode()).hexdigest()
    if not hmac.compare_digest(site_id, expected_site_id):
        raise LoginError("El token recibido no corresponde a este inicio de sesión.")

    return Credentials(token=token, private_token=private[0] if private else None)


async def login_with_browser(
    site: Site,
    *,
    timeout: float = LOGIN_TIMEOUT_SECONDS,
    headless: bool = False,
    notify: Callable[[str], None] = lambda _message: None,
) -> Credentials:
    """Open a browser for the student to log in and return the resulting credentials.

    ``notify`` tells the student what is going on, e.g. that a browser is being downloaded.
    """
    passport = secrets.token_hex(16)
    token_url: asyncio.Future[str] = asyncio.get_running_loop().create_future()

    def capture_token_redirect(response: Response) -> None:
        location = response.headers.get("location", "")
        if location.startswith(TOKEN_URL_PREFIX) and not token_url.done():
            token_url.set_result(location)

    def abort_if_window_closed(_page) -> None:
        if not token_url.done():
            token_url.set_exception(LoginError("Se cerró el navegador antes de terminar el login."))

    async with async_playwright() as playwright:
        # A fresh, cookie-less context guarantees a new login, which is when
        # Moodle also issues the private token.
        browser = await launch_browser(playwright, headless=headless, notify=notify)
        try:
            context = await browser.new_context()
            context.on("response", capture_token_redirect)
            page = await context.new_page()
            page.on("close", abort_if_window_closed)

            await page.goto(
                site.launch_url(service=SERVICE, passport=passport, url_scheme=URL_SCHEME)
            )
            try:
                url = await asyncio.wait_for(token_url, timeout)
            except TimeoutError:
                raise LoginError(f"No se completó el login en {timeout:.0f} segundos.") from None
        finally:
            await browser.close()

    return parse_token_url(url, site=site, passport=passport)


async def launch_browser(
    playwright: Playwright, *, headless: bool, notify: Callable[[str], None]
) -> Browser:
    """The student's Chrome or Edge, or else Playwright's Chromium, downloaded if needed."""
    for channel in INSTALLED_BROWSERS:
        try:
            return await playwright.chromium.launch(channel=channel, headless=headless)
        except PlaywrightError:
            continue  # not installed (or it would not start): try the next one
    if not Path(playwright.chromium.executable_path).exists():
        notify(
            "No se ha encontrado Chrome ni Edge: se descargará un navegador para el login "
            "(solo esta vez; ocupa unos 400 MB)."
        )
        await install_chromium()
    return await playwright.chromium.launch(headless=headless)


async def install_chromium() -> None:
    """Download Playwright's Chromium, showing its progress in the terminal. Only the
    full browser: the login shows it, so its separate headless build is not needed."""
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "playwright", "install", "--no-shell", "chromium"
    )
    if await process.wait() != 0:
        raise LoginError(
            "No se pudo descargar el navegador para el login. "
            "Instala Google Chrome o Microsoft Edge y vuelve a intentarlo."
        )
