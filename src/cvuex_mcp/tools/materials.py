from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from cvuex_mcp.campus import CourseNotEnrolledError
from cvuex_mcp.formatting import human_size, iso_datetime
from cvuex_mcp.materials.index import MaterialsIndex
from cvuex_mcp.materials.lock import SyncLockedError
from cvuex_mcp.materials.search import MaterialNotReadableError, read_material, search_materials
from cvuex_mcp.materials.sync import SyncProgress, synchronize
from cvuex_mcp.models import EstadoSincronizacion, ResultadosMateriales, TextoMaterial
from cvuex_mcp.runtime import (
    READ_ONLY,
    WRITES_LOCAL_FILES,
    campus_session,
    moodle_client,
    server_state,
)
from cvuex_mcp.storage import materials_dir

WAIT_SECONDS = 8
"""How long a call waits for the sync to end: clients cut tool calls short (opencode, 15 s)."""


async def sincronizar_materiales(
    ctx: Context,
    asignatura_id: Annotated[
        int | None,
        Field(description="Id (de mis_asignaturas) para una sola asignatura; si no, las en curso."),
    ] = None,
) -> EstadoSincronizacion:
    """Descarga al equipo del alumno los materiales de sus asignaturas (archivos, carpetas,
    páginas y libros), solo lo nuevo o modificado, en la carpeta indicada en `carpeta`.

    Descarga en segundo plano: si responde 'en_curso', vuelve a llamarla para ver el
    progreso; mientras tanto no empieza otra. Descargar no cuenta como haber visto el
    material en Moodle. Los materiales son solo para el estudio personal del alumno.
    """
    state = server_state(ctx)
    if not state.materials.running:
        async with campus_session(ctx) as campus:
            downloader = moodle_client(state, state.download_limiter)

            async def sync(progress: SyncProgress) -> None:
                await synchronize(campus, downloader, asignatura_id, progress)

            state.materials.start(
                sync, SyncProgress(), expected=(SyncLockedError, CourseNotEnrolledError)
            )
    await state.materials.wait(WAIT_SECONDS)
    return _report(state.materials.progress, running=state.materials.running)


def _report(progress: SyncProgress, *, running: bool) -> EstadoSincronizacion:
    if running:
        status = "en_curso"
    elif progress.error:
        status = "error"
    else:
        status = "terminada"
    return EstadoSincronizacion(
        estado=status,
        carpeta=str(materials_dir()),
        asignaturas=progress.courses,
        ficheros=progress.found,
        revisados=progress.checked,
        descargados=progress.downloaded,
        al_dia=progress.up_to_date,
        retirados=progress.removed,
        tamano_descargado=human_size(progress.downloaded_bytes),
        indexados=progress.indexed,
        no_buscables=progress.not_searchable,
        omitidos=progress.too_big,
        avisos=progress.warnings,
        error=progress.error,
        inicio=iso_datetime(int(progress.started_at)),
        fin=iso_datetime(int(progress.finished_at)) if progress.finished_at else None,
    )


async def buscar_en_materiales(
    consulta: Annotated[
        str, Field(min_length=2, description="Palabras que buscar: conceptos, términos, nombres.")
    ],
    asignatura_id: Annotated[
        int | None, Field(description="Id (de mis_asignaturas) para buscar solo en esa.")
    ] = None,
    limite: Annotated[int, Field(ge=1, le=30, description="Cuántos resultados como mucho.")] = 10,
) -> ResultadosMateriales:
    """Busca en el texto de los materiales descargados (PDF, Word, PowerPoint, páginas...)
    y dice en qué documento y página aparece cada coincidencia.

    Busca palabras, no significados: sin tildes ni mayúsculas, y las palabras largas
    también como prefijo. Si no encuentra nada, prueba con sinónimos o términos del
    temario, y en inglés (hay materiales en ese idioma). Solo busca en lo descargado con
    sincronizar_materiales; no consulta el campus.
    """
    index = MaterialsIndex()
    try:
        return search_materials(index, materials_dir(), consulta, asignatura_id, limite)
    finally:
        index.close()


async def leer_material(
    documento_id: Annotated[int, Field(description="El documento_id de buscar_en_materiales.")],
    desde: Annotated[
        int, Field(ge=1, description="Primera página, diapositiva o apartado que leer.")
    ] = 1,
    hasta: Annotated[
        int | None, Field(ge=1, description="Última que leer; si no, hasta donde quepa.")
    ] = None,
) -> TextoMaterial:
    """Lee el texto de un material descargado, por páginas (o diapositivas, o apartados),
    para responder con lo que dicen los apuntes y citarlos: documento y página.

    Devuelve un tamaño limitado; si queda más, `continua_en` dice desde dónde seguir.
    """
    index = MaterialsIndex()
    try:
        return read_material(index, materials_dir(), documento_id, desde, hasta)
    except MaterialNotReadableError as error:
        raise ToolError(str(error)) from error
    finally:
        index.close()


def register(mcp: MCPServer) -> None:
    mcp.add_tool(sincronizar_materiales, annotations=WRITES_LOCAL_FILES)
    mcp.add_tool(buscar_en_materiales, annotations=READ_ONLY)
    mcp.add_tool(leer_material, annotations=READ_ONLY)
