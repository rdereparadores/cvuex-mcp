"""Finding and reading the downloaded materials, citing where each text comes from."""

from pathlib import Path, PurePosixPath

from cvuex_mcp.materials.extract import NOT_SEARCHABLE
from cvuex_mcp.materials.index import Document, MaterialsIndex
from cvuex_mcp.models import CoincidenciaMaterial, ResultadosMateriales, TextoMaterial

MAX_READ_CHARS = 12_000
"""Per call to leer_material: enough for several pages without flooding the context."""
NOTHING_DOWNLOADED = "Aún no hay materiales descargados: usa sincronizar_materiales."


class MaterialNotReadableError(Exception):
    pass


def search_materials(
    index: MaterialsIndex, root: Path, query: str, course_id: int | None, limit: int
) -> ResultadosMateriales:
    matches, all_words = index.search(query, course_id=course_id, limit=limit)
    documents = index.documents()
    warnings = []
    if not documents:
        warnings.append(NOTHING_DOWNLOADED)
    not_searchable = [
        d for d in documents if d.status in NOT_SEARCHABLE and course_id in (None, d.course_id)
    ]
    if not_searchable:
        warnings.append(
            f"{len(not_searchable)} documentos no se pueden buscar (PDF escaneados o formatos "
            "antiguos .doc/.ppt) y no aparecen en los resultados."
        )
    return ResultadosMateriales(
        todas_las_palabras=all_words,
        resultados=[
            CoincidenciaMaterial(
                documento_id=match.document.id,
                documento=_name(match.document),
                asignatura=match.document.course,
                seccion=match.document.section,
                ubicacion=_location(match.document.unit, match.number, match.heading),
                numero=match.number,
                fragmento=match.snippet,
                archivo=str(root / match.document.path),
                url=match.document.module_url,
            )
            for match in matches
        ],
        avisos=warnings,
    )


def read_material(
    index: MaterialsIndex, root: Path, document_id: int, first: int, last: int | None
) -> TextoMaterial:
    document = index.document(document_id)
    if document is None:
        raise MaterialNotReadableError(
            f"No hay ningún documento {document_id}. Usa un documento_id de buscar_en_materiales."
        )
    if document.status != "ok":
        reason = NOT_SEARCHABLE.get(document.status) or {
            "no_soportado": "tiene un formato del que no se extrae texto",
        }.get(document.status, "no se pudo leer")
        raise MaterialNotReadableError(
            f"{_name(document)} {reason}. El alumno puede abrirlo en {root / document.path}."
        )

    last_part = index.last_number(document_id)
    parts = index.parts(document_id, first, last if last is not None else last_part)
    blocks, read, used = [], [], 0
    for number, heading, text in parts:
        block = f"[{_location(document.unit, number, heading).capitalize()}]\n{text}"
        if read and used + len(block) > MAX_READ_CHARS:
            break
        blocks.append(block[:MAX_READ_CHARS])
        read.append(number)
        used += len(block)
    unread = [number for number, _, _ in parts if number > (read[-1] if read else first - 1)]
    return TextoMaterial(
        documento_id=document.id,
        documento=_name(document),
        asignatura=document.course,
        seccion=document.section,
        unidad=document.unit,
        total=last_part,
        desde=read[0] if read else first,
        hasta=read[-1] if read else first,
        texto="\n\n".join(blocks) or f"No hay texto entre {first} y {last or last_part}.",
        continua_en=unread[0] if unread else None,
        archivo=str(root / document.path),
        url=document.module_url,
    )


def _name(document: Document) -> str:
    return PurePosixPath(document.path).name


def _location(unit: str, number: int, heading: str | None) -> str:
    """``("página", 12, None)`` → ``"página 12"``; headings go in brackets."""
    return f"{unit} {number} ({heading})" if heading else f"{unit} {number}"
