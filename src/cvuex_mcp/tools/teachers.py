from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from cvuex_mcp.campus import CourseNotEnrolledError
from cvuex_mcp.campus.teachers import course_teachers
from cvuex_mcp.models import ListaProfesorado
from cvuex_mcp.runtime import READ_ONLY, campus_session


async def contacto_profesorado(
    ctx: Context,
    asignatura_id: Annotated[
        int | None, Field(description="Id (de mis_asignaturas) para ver solo esa asignatura.")
    ] = None,
) -> ListaProfesorado:
    """Muestra los profesores de las asignaturas en curso (o de la indicada), como
    aparecen en la ficha de cada asignatura: nombre, correo y lo que ponen en su perfil.

    Las tutorías solo aparecen si el profesor las pone en su perfil, y casi nunca lo
    hacen: si no están, remite a la guía docente de la asignatura, sin inventarlas.
    """
    async with campus_session(ctx) as campus:
        try:
            return await course_teachers(campus, asignatura_id)
        except CourseNotEnrolledError as error:
            raise ToolError(str(error)) from error


def register(mcp: MCPServer) -> None:
    mcp.add_tool(contacto_profesorado, annotations=READ_ONLY)
