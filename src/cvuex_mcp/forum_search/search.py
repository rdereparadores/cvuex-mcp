"""Search results for the assistant, and how up to date the index is."""

from cvuex_mcp.formatting import iso_datetime
from cvuex_mcp.forum_search.index import ForumIndex
from cvuex_mcp.forum_search.refresh import ForumProgress
from cvuex_mcp.models import CoincidenciaForo, ResultadosForos


def search_forums(
    index: ForumIndex,
    query: str,
    course_id: int | None,
    limit: int,
    *,
    progress: ForumProgress | None,
    refreshing: bool,
) -> ResultadosForos:
    matches, all_words = index.search(query, course_id=course_id, limit=limit)
    warnings = []
    if refreshing and progress:
        warnings.append(
            f"Actualizando el índice de los foros: {progress.checked} de "
            f"{progress.discussions} debates revisados por ahora."
        )
    elif progress and progress.error:
        warnings.append(f"No se pudo actualizar el índice de los foros: {progress.error}")
    if progress:
        warnings += progress.warnings
    return ResultadosForos(
        todas_las_palabras=all_words,
        indice_al_dia=not refreshing,
        debates_indexados=index.count(course_id),
        resultados=[
            CoincidenciaForo(
                asignatura=match.discussion.course,
                foro=match.discussion.forum,
                titulo=match.discussion.title,
                autor=match.author,
                fecha=iso_datetime(match.created),
                fragmento=match.snippet,
                respuestas=match.discussion.replies,
                debate_id=match.discussion.id,
                url=match.discussion.url,
            )
            for match in matches
        ],
        avisos=warnings,
    )
