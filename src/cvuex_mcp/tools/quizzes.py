from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from cvuex_mcp.campus.quizzes import QuizReviewError, quizzes, review_attempt
from cvuex_mcp.models import ListaCuestionarios, RevisionCuestionario
from cvuex_mcp.runtime import READ_ONLY, campus_session


async def cuestionarios(
    ctx: Context,
    asignatura_id: Annotated[
        int | None, Field(description="Id (de mis_asignaturas) para ver solo esa asignatura.")
    ] = None,
) -> ListaCuestionarios:
    """Muestra los cuestionarios de las asignaturas en curso, con sus fechas y los
    intentos terminados del alumno (nota y comentario general, si el profesor los deja ver).

    Para ver las preguntas de un intento, usa revisar_cuestionario con su intento_id.
    """
    async with campus_session(ctx) as campus:
        return await quizzes(campus, asignatura_id)


async def revisar_cuestionario(
    ctx: Context,
    intento_id: Annotated[int, Field(description="El intento_id que da cuestionarios.")],
) -> RevisionCuestionario:
    """Muestra la revisión de un intento terminado: nota, comentario general y, por
    pregunta, el enunciado, lo que respondió el alumno, si es correcto, la puntuación, la
    retroalimentación y la respuesta correcta.

    Solo muestra lo que el profesor permite revisar en el campus, así que algunos datos
    pueden faltar. No sirve para intentos en curso: ayudar a responder un cuestionario
    abierto no está permitido.
    """
    async with campus_session(ctx) as campus:
        try:
            return await review_attempt(campus, intento_id)
        except QuizReviewError as error:
            raise ToolError(str(error)) from error


def register(mcp: MCPServer) -> None:
    mcp.add_tool(cuestionarios, annotations=READ_ONLY)
    mcp.add_tool(revisar_cuestionario, annotations=READ_ONLY)
