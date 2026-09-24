"""What tools share while the server runs, and how a tool reaches the campus."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import httpx
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from cvuex_mcp.cache import TTLCache
from cvuex_mcp.campus import Campus
from cvuex_mcp.credentials import CredentialStore
from cvuex_mcp.moodle import InvalidTokenError, MoodleClient, MoodleError, new_http_client
from cvuex_mcp.rate_limit import RateLimiter
from cvuex_mcp.session import NotLoggedInError, expired_session_message, load_token
from cvuex_mcp.sites import AVUEX
from cvuex_mcp.state import PersistentState

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=True)


@dataclass
class ServerState:
    """Shared by every tool call during the server's lifetime."""

    http: httpx.AsyncClient
    rate_limiter: RateLimiter
    store: CredentialStore = field(default_factory=CredentialStore)
    cache: TTLCache = field(default_factory=TTLCache)
    saved: PersistentState = field(default_factory=PersistentState)
    cached_token: str | None = None
    """Token whose answers are in the cache."""


@asynccontextmanager
async def lifespan(_server: MCPServer) -> AsyncIterator[ServerState]:
    async with new_http_client() as http:
        yield ServerState(http=http, rate_limiter=RateLimiter())


def server_state(ctx: Context) -> ServerState:
    return ctx.request_context.lifespan_context


@asynccontextmanager
async def campus_session(ctx: Context) -> AsyncIterator[Campus]:
    """Give a tool access to the campus, turning failures into messages for the assistant.

    The token is read on every call, so logging in again takes effect
    without restarting the server.
    """
    state = server_state(ctx)
    try:
        token = load_token(state.store)
        if token != state.cached_token:  # new session: cached answers belong to the old one
            state.cache.clear()
            state.cached_token = token
        moodle = MoodleClient(AVUEX, token, http=state.http, rate_limiter=state.rate_limiter)
        yield Campus(moodle, state.cache)
    except NotLoggedInError as error:
        raise ToolError(str(error)) from error
    except InvalidTokenError as error:
        raise ToolError(expired_session_message()) from error
    except MoodleError as error:
        raise ToolError(f"Moodle devolvió un error ({error.errorcode}): {error}") from error
    except httpx.HTTPError as error:
        raise ToolError(f"No se pudo conectar con {AVUEX.name}: {error}") from error
