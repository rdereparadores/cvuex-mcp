"""SSO login through the UEx CAS, the same way the official Moodle app does it.

1. A real browser opens ``launch.php`` with a random ``passport``.
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

from playwright.async_api import Response, async_playwright

from cvuex_mcp.credentials import Credentials
from cvuex_mcp.sites import Site

SERVICE = "moodle_mobile_app"
URL_SCHEME = "moodlemobile"
TOKEN_URL_PREFIX = f"{URL_SCHEME}://token="
LOGIN_TIMEOUT_SECONDS = 300


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
) -> Credentials:
    """Open a browser for the student to log in and return the resulting credentials."""
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
        browser = await playwright.chromium.launch(headless=headless)
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
