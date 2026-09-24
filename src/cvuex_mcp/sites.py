"""The Moodle platform this server works with.

The UEx Virtual Campus has several Moodle platforms; for now only AVUEx,
where students' degree courses live, is supported.
"""

from dataclasses import dataclass
from urllib.parse import urlencode


@dataclass(frozen=True)
class Site:
    key: str
    name: str
    url: str
    """Moodle's ``wwwroot``, without a trailing slash. It must match the
    server's value exactly, because the SSO login signs its response with it."""

    @property
    def rest_url(self) -> str:
        return f"{self.url}/webservice/rest/server.php"

    def launch_url(self, *, service: str, passport: str, url_scheme: str) -> str:
        """URL that starts the SSO login used by the official Moodle app."""
        query = urlencode({"service": service, "passport": passport, "urlscheme": url_scheme})
        return f"{self.url}/admin/tool/mobile/launch.php?{query}"


AVUEX = Site(
    key="avuex",
    name="AVUEx (aulas regladas)",
    url="https://campusvirtual.unex.es/zonauex/avuex",
)
