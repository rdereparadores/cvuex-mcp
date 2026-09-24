import time
from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from pydantic import Field

from cvuex_mcp.campus.changes import course_changes
from cvuex_mcp.models import ListaNovedades
from cvuex_mcp.runtime import READ_ONLY, campus_session, server_state
from cvuex_mcp.state import PersistentState

LAST_CHANGES_CHECK = "novedades_ultima_consulta"
FIRST_CHANGES_LOOKBACK_HOURS = 7 * 24


def changes_since(saved: PersistentState, hours: int | None, now: int) -> int:
    """Explicit hours win; otherwise, since the last check (a week, the first time)."""
    if hours is not None:
        return now - hours * 3600
    return saved.get(LAST_CHANGES_CHECK) or now - FIRST_CHANGES_LOOKBACK_HOURS * 3600


async def novedades(
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
    saved = server_state(ctx).saved
    now = int(time.time())
    async with campus_session(ctx) as campus:
        result = await course_changes(campus, changes_since(saved, desde_horas, now), asignatura_id)
    # Only a full default check moves the mark, so no course's changes get skipped.
    if desde_horas is None and asignatura_id is None:
        saved.set(LAST_CHANGES_CHECK, now)
    return result


def register(mcp: MCPServer) -> None:
    mcp.add_tool(novedades, annotations=READ_ONLY)
