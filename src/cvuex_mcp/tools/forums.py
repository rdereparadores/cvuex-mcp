import time
from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from cvuex_mcp.campus import CourseNotEnrolledError
from cvuex_mcp.campus.forums import DiscussionNotFoundError, announcements, read_discussion
from cvuex_mcp.forum_search.index import ForumIndex
from cvuex_mcp.forum_search.refresh import ForumProgress, is_stale, refresh_forums
from cvuex_mcp.forum_search.search import search_forums
from cvuex_mcp.models import Debate, ListaAvisos, ResultadosForos
from cvuex_mcp.runtime import READ_ONLY, campus_session, server_state

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


WAIT_SECONDS = 6
"""How long a search waits for the index to be brought up to date (opencode: 15 s)."""


async def buscar_en_foros(
    ctx: Context,
    consulta: Annotated[
        str, Field(min_length=2, description="Palabras que buscar en los mensajes.")
    ],
    asignatura_id: Annotated[
        int | None, Field(description="Id (de mis_asignaturas) para buscar solo en esa.")
    ] = None,
    limite: Annotated[int, Field(ge=1, le=30, description="Cuántos debates como mucho.")] = 10,
) -> ResultadosForos:
    """Busca en los mensajes de todos los foros de las asignaturas en curso (o de la
    indicada): "¿alguien preguntó ya por esto?". Da un resultado por debate, con el
    fragmento del mensaje que coincide; leer_debate muestra el debate entero.

    Busca palabras, no significados: si no encuentra nada, reformula. La primera vez (y
    cada 10 minutos) pone al día un índice local en segundo plano; mientras tanto puede
    faltar algún resultado ('indice_al_dia': false). Para indexar las respuestas, Moodle
    las marca como leídas si el alumno sigue ese foro.
    """
    state = server_state(ctx)
    async with campus_session(ctx) as campus:
        try:
            courses = await campus.enrolled_courses(asignatura_id)
        except CourseNotEnrolledError as error:
            raise ToolError(str(error)) from error
        index = ForumIndex()
        try:
            stale = [c for c in courses if is_stale(index, c.id, time.time())]
        finally:
            index.close()
        if stale and not state.forums.running:

            async def refresh(progress: ForumProgress) -> None:
                await refresh_forums(campus, stale, progress)

            state.forums.start(refresh, ForumProgress())
    await state.forums.wait(WAIT_SECONDS)

    index = ForumIndex()
    try:
        return search_forums(
            index,
            consulta,
            asignatura_id,
            limite,
            progress=state.forums.progress,
            refreshing=state.forums.running,
        )
    finally:
        index.close()


def register(mcp: MCPServer) -> None:
    mcp.add_tool(avisos, annotations=READ_ONLY)
    mcp.add_tool(leer_debate, annotations=MARKS_AS_READ)
    mcp.add_tool(buscar_en_foros, annotations=MARKS_AS_READ)
