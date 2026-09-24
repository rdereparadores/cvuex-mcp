from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from pydantic import Field

from cvuex_mcp.campus.assignments import submission_statuses
from cvuex_mcp.models import ListaEntregas
from cvuex_mcp.runtime import READ_ONLY, campus_session


async def estado_entregas(
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
        return await submission_statuses(campus, asignatura_id, only_pending=solo_pendientes)


def register(mcp: MCPServer) -> None:
    mcp.add_tool(estado_entregas, annotations=READ_ONLY)
