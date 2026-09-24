from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from cvuex_mcp.campus.grades import (
    CourseGradesNotAvailableError,
    course_grades,
    grades_overview,
)
from cvuex_mcp.models import Calificaciones
from cvuex_mcp.runtime import READ_ONLY, campus_session


async def calificaciones(
    ctx: Context,
    asignatura_id: Annotated[
        int | None,
        Field(description="Id (de mis_asignaturas) para ver el detalle de esa asignatura."),
    ] = None,
) -> Calificaciones:
    """Muestra las calificaciones del alumno.

    Sin asignatura, la nota total de cada asignatura. Con asignatura, además, cada
    actividad calificable con su nota, peso y comentarios del profesor, y los totales
    de cada categoría. Solo aparece lo que el profesor deja ver al alumno.
    """
    async with campus_session(ctx) as campus:
        if asignatura_id is None:
            return await grades_overview(campus)
        try:
            return await course_grades(campus, asignatura_id)
        except CourseGradesNotAvailableError as error:
            raise ToolError(str(error)) from error


def register(mcp: MCPServer) -> None:
    mcp.add_tool(calificaciones, annotations=READ_ONLY)
