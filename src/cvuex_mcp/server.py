"""MCP server exposing the student's Virtual Campus to an AI assistant."""

import logging
import time
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
from cvuex_mcp.models import ListaAsignaturas, ListaEntregas, ListaNovedades, ListaPlazos
from cvuex_mcp.moodle import InvalidTokenError, MoodleClient, MoodleError, new_http_client
from cvuex_mcp.rate_limit import RateLimiter
from cvuex_mcp.session import NotLoggedInError, expired_session_message, load_token
from cvuex_mcp.sites import AVUEX
from cvuex_mcp.state import PersistentState

# httpx logs every request URL, and file downloads carry the token in the URL.
logging.getLogger("httpx").setLevel(logging.WARNING)


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


@mcp.tool(name="proximos_plazos", annotations=READ_ONLY)
async def upcoming_deadlines(
    ctx: Context,
    dias: Annotated[int, Field(ge=1, le=90, description="Cuántos días hacia delante mirar.")] = 14,
    asignatura_id: Annotated[
        int | None, Field(description="Id (de mis_asignaturas) para ver solo esa asignatura.")
    ] = None,
) -> ListaPlazos:
    """Lista lo que el alumno tiene pendiente con fecha: entregas de tareas, cierres de
    cuestionarios y otras actividades, ordenado por fecha.

    Solo aparece lo que aún requiere una acción del alumno (una tarea ya entregada no
    sale). Incluye lo vencido en los últimos 30 días que sigue pendiente, marcado con
    vencido = true.
    """
    async with campus_session(ctx) as campus:
        return await campus.deadlines(dias, asignatura_id)


@mcp.tool(name="estado_entregas", annotations=READ_ONLY)
async def submission_status(
    ctx: Context,
    asignatura_id: Annotated[
        int | None, Field(description="Id (de mis_asignaturas) para ver solo esa asignatura.")
    ] = None,
    solo_pendientes: Annotated[
        bool, Field(description="false para incluir también las entregadas y su calificación.")
    ] = True,
) -> ListaEntregas:
    """Muestra el estado de las tareas del alumno: sin entregar, en borrador o entregadas,
    con la fecha límite, la nota y los comentarios del profesor cuando se han publicado.

    Sin asignatura_id, revisa las asignaturas en curso. Puede tardar unos segundos,
    porque cada tarea se consulta por separado.
    """
    async with campus_session(ctx) as campus:
        return await campus.submissions(asignatura_id, only_pending=solo_pendientes)


LAST_CHANGES_CHECK = "novedades_ultima_consulta"
FIRST_CHANGES_LOOKBACK_HOURS = 7 * 24


def changes_since(saved: PersistentState, hours: int | None, now: int) -> int:
    """Explicit hours win; otherwise, since the last check (a week, the first time)."""
    if hours is not None:
        return now - hours * 3600
    return saved.get(LAST_CHANGES_CHECK) or now - FIRST_CHANGES_LOOKBACK_HOURS * 3600


@mcp.tool(name="novedades", annotations=READ_ONLY)
async def changes(
    ctx: Context,
    desde_horas: Annotated[
        int | None,
        Field(
            ge=1,
            le=60 * 24,
            description="Mirar las últimas N horas en vez de desde la última consulta.",
        ),
    ] = None,
    asignatura_id: Annotated[
        int | None, Field(description="Id (de mis_asignaturas) para ver solo esa asignatura.")
    ] = None,
) -> ListaNovedades:
    """Resume qué ha cambiado en las asignaturas: materiales o actividades nuevas o
    modificadas, debates nuevos en los foros, calificaciones...

    Por defecto, desde la última vez que se consultaron las novedades (la primera
    vez, la última semana); `desde` indica el momento exacto.
    """
    state: ServerState = ctx.request_context.lifespan_context
    now = int(time.time())
    async with campus_session(ctx) as campus:
        result = await campus.changes(changes_since(state.saved, desde_horas, now), asignatura_id)
    # Only a full default check moves the mark, so no course's changes get skipped.
    if desde_horas is None and asignatura_id is None:
        state.saved.set(LAST_CHANGES_CHECK, now)
    return result
