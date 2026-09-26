from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from cvuex_mcp.calendar_export import MAX_DAYS, export_calendar
from cvuex_mcp.campus import CourseNotEnrolledError
from cvuex_mcp.models import CalendarioExportado
from cvuex_mcp.runtime import WRITES_LOCAL_FILES, campus_session


async def exportar_calendario(
    ctx: Context,
    dias: Annotated[
        int, Field(ge=1, le=MAX_DAYS, description="Cuántos días hacia delante.")
    ] = MAX_DAYS,
    asignatura_id: Annotated[
        int | None, Field(description="Id (de mis_asignaturas) para exportar solo esa asignatura.")
    ] = None,
) -> CalendarioExportado:
    """Guarda en el equipo del alumno un fichero .ics con lo que viene en el calendario
    (lo mismo que proximos_plazos, sin lo vencido), para importarlo en Google Calendar,
    Outlook u otro calendario. Cada vez que se exporta, el fichero se sustituye.

    El fichero no se sube a ningún sitio: el alumno lo importa. Explícale cómo, con
    como_importar.
    """
    async with campus_session(ctx) as campus:
        try:
            return await export_calendar(campus, dias, asignatura_id)
        except CourseNotEnrolledError as error:
            raise ToolError(str(error)) from error


def register(mcp: MCPServer) -> None:
    mcp.add_tool(exportar_calendario, annotations=WRITES_LOCAL_FILES)
