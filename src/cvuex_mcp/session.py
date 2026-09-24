"""The student's stored session: loading its token and the related messages."""

from cvuex_mcp.credentials import CredentialStore
from cvuex_mcp.moodle import MoodleClient
from cvuex_mcp.sites import AVUEX, Site

LOGIN_HINT = "Inicia sesión con: cvuex-mcp login"


def expired_session_message(site: Site = AVUEX) -> str:
    return f"La sesión en {site.name} ha caducado. {LOGIN_HINT}"


class NotLoggedInError(Exception):
    pass


def load_token(store: CredentialStore, site: Site = AVUEX) -> str:
    credentials = store.load(site.key)
    if credentials is None:
        raise NotLoggedInError(f"No hay ninguna sesión iniciada en {site.name}. {LOGIN_HINT}")
    return credentials.token


def open_client(store: CredentialStore | None = None, site: Site = AVUEX) -> MoodleClient:
    """A standalone client, for one-off commands."""
    return MoodleClient(site, load_token(store or CredentialStore(), site))
