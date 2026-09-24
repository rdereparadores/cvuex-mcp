from typing import Annotated, Literal

from mcp.server.mcpserver import Context, MCPServer
from pydantic import Field

from cvuex_mcp.campus import CourseClassification
from cvuex_mcp.models import ListaAsignaturas
from cvuex_mcp.runtime import READ_ONLY, campus_session

CourseState = Literal["en_curso", "pasadas", "futuras", "todas"]

COURSE_STATES: dict[CourseState, CourseClassification] = {
    "en_curso": "inprogress",
    "pasadas": "past",
    "futuras": "future",
    "todas": "all",
}


async def mis_asignaturas(
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


def register(mcp: MCPServer) -> None:
    mcp.add_tool(mis_asignaturas, annotations=READ_ONLY)
