from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from pydantic import Field

from cvuex_mcp.campus.deadlines import upcoming_deadlines
from cvuex_mcp.models import ListaPlazos
from cvuex_mcp.runtime import READ_ONLY, campus_session


async def proximos_plazos(
    ctx: Context,
    dias: Annotated[int, Field(ge=1, le=90, description="Cuántos días hacia delante mirar.")] = 14,
    asignatura_id: Annotated[
        int | None, Field(description="Id (de mis_asignaturas) para ver solo esa asignatura.")
    ] = None,
) -> ListaPlazos:
    """Lista lo que tiene el alumno en el calendario, ordenado por fecha: entregas de
    tareas, cierres y aperturas de actividades, eventos que añade el profesor (exámenes,
    sesiones...) y eventos personales.

    requiere_accion = true marca lo que Moodle espera que el alumno haga (entregar,
    responder...); desaparece cuando ya está hecho. Esos pendientes se incluyen aunque
    hayan vencido en los últimos 30 días (vencido = true). El resto es informativo.
    """
    async with campus_session(ctx) as campus:
        return await upcoming_deadlines(campus, dias, asignatura_id)


def register(mcp: MCPServer) -> None:
    mcp.add_tool(proximos_plazos, annotations=READ_ONLY)
