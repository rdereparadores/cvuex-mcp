from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from cvuex_mcp.campus.forums import DiscussionNotFoundError, announcements, read_discussion
from cvuex_mcp.models import Debate, ListaAvisos
from cvuex_mcp.runtime import READ_ONLY, campus_session

# Reading a discussion may mark its posts as read: the only change a tool can make.
MARKS_AS_READ = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=True
)


async def avisos(
    ctx: Context,
    asignatura_id: Annotated[
        int | None, Field(description="Id (de mis_asignaturas) para ver solo esa asignatura.")
    ] = None,
    dias: Annotated[
        int, Field(ge=1, le=365, description="Debates publicados o con respuestas en estos días.")
    ] = 30,
    limite: Annotated[int, Field(ge=1, le=50, description="Cuántos mostrar como mucho.")] = 20,
) -> ListaAvisos:
    """Muestra los avisos de los profesores y los debates de los foros generales de las
    asignaturas en curso, del más reciente al más antiguo, con el comienzo del mensaje.

    Consultarlos no los marca como leídos. Para leer un debate entero, usa leer_debate
    con su debate_id.
    """
    async with campus_session(ctx) as campus:
        return await announcements(campus, dias, limite, asignatura_id)


async def leer_debate(
    ctx: Context,
    debate_id: Annotated[int, Field(description="El debate_id que da avisos.")],
) -> Debate:
    """Muestra todos los mensajes de un debate de un foro, completos y en orden cronológico.

    Atención: si el alumno tiene activado el seguimiento de mensajes no leídos en ese
    foro, Moodle los marca como leídos. Úsala solo cuando el alumno quiera leer el debate.
    """
    async with campus_session(ctx) as campus:
        try:
            return await read_discussion(campus, debate_id)
        except DiscussionNotFoundError as error:
            raise ToolError(str(error)) from error


def register(mcp: MCPServer) -> None:
    mcp.add_tool(avisos, annotations=READ_ONLY)
    mcp.add_tool(leer_debate, annotations=MARKS_AS_READ)
