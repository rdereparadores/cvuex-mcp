"""MCP server exposing the student's Virtual Campus to an AI assistant."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Annotated, Literal

import httpx
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from cvuex_mcp.cache import TTLCache
from cvuex_mcp.campus import Campus, CourseClassification
from cvuex_mcp.credentials import CredentialStore
from cvuex_mcp.models import ListaAsignaturas
from cvuex_mcp.moodle import InvalidTokenError, MoodleClient, MoodleError, new_http_client
from cvuex_mcp.rate_limit import RateLimiter
from cvuex_mcp.session import NotLoggedInError, expired_session_message, load_token
from cvuex_mcp.sites import AVUEX

# httpx logs every request URL, and file downloads carry the token in the URL.
logging.getLogger("httpx").setLevel(logging.WARNING)


@dataclass
class ServerState:
    """Shared by every tool call during the server's lifetime."""

    http: httpx.AsyncClient
    store: CredentialStore = field(default_factory=CredentialStore)
    rate_limiter: RateLimiter = field(default_factory=RateLimiter)
    cache: TTLCache = field(default_factory=TTLCache)
    cached_token: str | None = None
    """Token whose answers are in the cache."""


@asynccontextmanager
async def lifespan(_server: MCPServer) -> AsyncIterator[ServerState]:
    async with new_http_client() as http:
        yield ServerState(http=http)


mcp = MCPServer(
    name="cvuex",
    instructions=(
        "Acceso de solo lectura a las aulas virtuales (AVUEx) del Campus Virtual de la "
        "Universidad de Extremadura, con la cuenta del propio alumno."
    ),
    lifespan=lifespan,
)

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=True)


@asynccontextmanager
async def campus_session(ctx: Context) -> AsyncIterator[Campus]:
    """Give a tool access to the campus, turning failures into messages for the assistant.

    The token is read on every call, so logging in again takes effect
    without restarting the server.
    """
    state: ServerState = ctx.request_context.lifespan_context
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


@mcp.tool(name="quien_soy", annotations=READ_ONLY)
async def whoami(ctx: Context) -> dict[str, str]:
    """Indica con qué cuenta del Campus Virtual de la UEx está conectado el servidor."""
    async with campus_session(ctx) as campus:
        info = await campus.site_info()
    return {"nombre": info.full_name, "usuario": info.username, "plataforma": info.site_name}


CourseState = Literal["en_curso", "pasadas", "futuras", "todas"]

COURSE_STATES: dict[CourseState, CourseClassification] = {
    "en_curso": "inprogress",
    "pasadas": "past",
    "futuras": "future",
    "todas": "all",
}


@mcp.tool(name="mis_asignaturas", annotations=READ_ONLY)
async def my_courses(
    ctx: Context,
    estado: Annotated[
        CourseState, Field(description="Qué asignaturas listar según sus fechas.")
    ] = "en_curso",
) -> ListaAsignaturas:
    """Lista las asignaturas en las que está matriculado el alumno.

    Úsala para saber qué cursa y para obtener el id de una asignatura, que
    otras herramientas aceptan para filtrar.
    """
    async with campus_session(ctx) as campus:
        courses = await campus.courses(COURSE_STATES[estado])
    return ListaAsignaturas(asignaturas=courses)
