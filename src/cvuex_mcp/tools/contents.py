from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from cvuex_mcp.campus.contents import CourseNotAvailableError, course_contents
from cvuex_mcp.models import ContenidoAsignatura
from cvuex_mcp.runtime import READ_ONLY, campus_session


async def contenido_asignatura(
    ctx: Context,
    asignatura_id: Annotated[int, Field(description="Id de la asignatura (de mis_asignaturas).")],
    seccion: Annotated[
        int | None,
        Field(ge=0, description="Número de sección (tema) para ver solo esa y sus subsecciones."),
    ] = None,
) -> ContenidoAsignatura:
    """Muestra el contenido de una asignatura como en su página del campus: secciones o
    temas con sus materiales (archivos, carpetas, páginas, enlaces) y actividades, con
    fechas, restricciones de acceso y si el alumno las ha completado.

    No descarga nada ni cuenta como haber visto los materiales en Moodle.
    """
    async with campus_session(ctx) as campus:
        try:
            return await course_contents(campus, asignatura_id, seccion)
        except CourseNotAvailableError as error:
            raise ToolError(str(error)) from error


def register(mcp: MCPServer) -> None:
    mcp.add_tool(contenido_asignatura, annotations=READ_ONLY)
