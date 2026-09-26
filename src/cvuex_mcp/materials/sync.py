"""Bring the local copy of the course materials up to date, and index it.

Incremental: only new or modified files are downloaded. Files the teacher
removes from the campus keep their local copy, flagged in the manifest, and
stay searchable. Nothing the student put in the folder is ever overwritten.
"""

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

import httpx

from cvuex_mcp.campus.core import Campus
from cvuex_mcp.formatting import human_size
from cvuex_mcp.jobs import JobProgress
from cvuex_mcp.materials.catalog import MAX_FILE_BYTES, RemoteFile, course_catalog
from cvuex_mcp.materials.extract import EXTRACTION_VERSION, NOT_SEARCHABLE, extract
from cvuex_mcp.materials.index import DocumentInfo, MaterialsIndex
from cvuex_mcp.materials.layout import numbered, safe_name
from cvuex_mcp.materials.lock import SyncLock
from cvuex_mcp.materials.manifest import Entry, Manifest
from cvuex_mcp.models import Asignatura
from cvuex_mcp.moodle import InvalidTokenError, MoodleClient, MoodleError
from cvuex_mcp.storage import materials_dir


@dataclass
class SyncProgress(JobProgress):
    courses: list[str] = field(default_factory=list)
    found: int = 0
    checked: int = 0
    downloaded: int = 0
    up_to_date: int = 0
    removed: int = 0
    downloaded_bytes: int = 0
    indexed: int = 0
    not_searchable: list[str] = field(default_factory=list)
    """Study documents that can't be searched, and why (scanned PDFs, old formats)."""
    too_big: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class Library:
    """Where the materials go: the student's folder, and the manifest and index."""

    root: Path
    manifest: Manifest
    index: MaterialsIndex


FileEvent = Callable[[str, RemoteFile, Path], None]
"""Called with "descargado", "al_dia" or "error", the file and its local path."""


async def synchronize(
    campus: Campus,
    downloader: MoodleClient,
    course_id: int | None,
    progress: SyncProgress,
    *,
    root: Path | None = None,
    manifest_path: Path | None = None,
    lock_path: Path | None = None,
    on_file: FileEvent | None = None,
) -> None:
    """Sync one course, or those in progress: what both the MCP tool and the CLI run."""
    courses = await campus.enrolled_courses(course_id)
    with SyncLock(lock_path) as lock:
        library = Library(
            root or materials_dir(), Manifest(manifest_path), MaterialsIndex(manifest_path)
        )
        try:
            await sync_materials(campus, downloader, library, courses, progress, lock, on_file)
        finally:
            library.manifest.close()
            library.index.close()


async def sync_materials(
    campus: Campus,
    downloader: MoodleClient,
    library: Library,
    courses: list[Asignatura],
    progress: SyncProgress,
    lock: SyncLock,
    on_file: FileEvent | None = None,
) -> None:
    """Download what's new in ``courses`` to the library, and index it.

    An expired session stops everything; any other failure only skips that file.
    """
    progress.courses = [course.nombre for course in courses]
    catalogs = []
    for course in courses:
        try:
            catalog = await course_catalog(campus, course.id)
        except InvalidTokenError:
            raise
        except MoodleError as error:
            progress.warnings.append(f"No se pudo consultar {course.nombre}: {error}")
            continue
        catalogs.append((course, catalog))
        progress.found += len(catalog.files)
        progress.too_big += [
            f"{course.nombre}: {remote.path} ({human_size(remote.size)}) supera "
            f"{human_size(MAX_FILE_BYTES)}; descárgalo desde el campus."
            for remote in catalog.too_big
        ]

    for course, catalog in catalogs:
        folder = library.manifest.course_folder(course.id, course.nombre, safe_name(course.nombre))
        for remote in catalog.files:
            entry = await _sync_file(
                downloader, library, course.id, folder, remote, progress, on_file
            )
            if entry:
                await _index(library, entry, course.nombre, progress)
            progress.checked += 1
            lock.refresh()
        in_campus = {remote.key for remote in catalog.files + catalog.too_big}
        progress.removed += library.manifest.mark_removed(course.id, in_campus)


async def _sync_file(
    downloader: MoodleClient,
    library: Library,
    course_id: int,
    folder: str,
    remote: RemoteFile,
    progress: SyncProgress,
    on_file: FileEvent | None,
) -> Entry | None:
    """The file's manifest entry once it is up to date locally; None if it failed."""
    root, manifest = library.root, library.manifest
    known = manifest.get(course_id, remote.key)
    # A file keeps its path once downloaded, even if new files would now take it.
    path = known.path if known else _free_path(root, manifest, f"{folder}/{remote.path}")
    local = root / path
    if (
        known
        and (known.size, known.timemodified) == (remote.size, remote.timemodified)
        and local.exists()
    ):
        progress.up_to_date += 1
        if not known.in_campus:  # back in the campus
            known = replace(known, in_campus=True)
            manifest.save(known)
        _notify(on_file, "al_dia", remote, local)
        return known
    try:
        size = await downloader.download(remote.file_url, local)
    except InvalidTokenError:
        raise
    except (MoodleError, httpx.HTTPError, OSError) as error:
        progress.warnings.append(f"No se pudo descargar {folder}/{remote.path}: {_reason(error)}")
        _notify(on_file, "error", remote, local)
        return None
    entry = Entry(
        course_id=course_id,
        key=remote.key,
        path=path,
        section=remote.section,
        module=remote.module,
        module_url=remote.module_url,
        kind=remote.kind,
        size=remote.size,
        timemodified=remote.timemodified,
        downloaded_at=int(time.time()),
    )
    manifest.save(entry)
    progress.downloaded += 1
    progress.downloaded_bytes += size
    _notify(on_file, "descargado", remote, local)
    return entry


async def _index(library: Library, entry: Entry, course: str, progress: SyncProgress) -> None:
    """Index the file's text, unless it is already indexed as it is now."""
    local = library.root / entry.path
    stat = local.stat()
    stamp = f"{EXTRACTION_VERSION}:{stat.st_size}:{stat.st_mtime_ns}"
    if library.index.is_current(entry.path, stamp):
        return
    # Reading a big PDF takes a while: off the event loop, so other tools keep answering.
    extraction = await asyncio.to_thread(extract, local)
    info = DocumentInfo(
        path=entry.path,
        course_id=entry.course_id,
        course=course,
        section=entry.section,
        module=entry.module,
        module_url=entry.module_url,
        stamp=stamp,
    )
    library.index.store(info, extraction)
    if extraction.status == "ok":
        progress.indexed += 1
    elif extraction.status in NOT_SEARCHABLE:
        progress.not_searchable.append(f"{entry.path}: {NOT_SEARCHABLE[extraction.status]}")
    elif extraction.status == "error":
        progress.warnings.append(f"No se pudo leer {entry.path}: {extraction.error}")


def _free_path(root: Path, manifest: Manifest, wanted: str) -> str:
    """``wanted``, or a numbered variant, not used by another campus file nor by
    anything the student put in the folder."""
    path, copy = wanted, 1
    while manifest.path_owner(path) or (root / path).exists():
        copy += 1
        stem, _, name = wanted.rpartition("/")
        path = f"{stem}/{numbered(name, copy)}"
    return path


def _reason(error: Exception) -> str:
    """Short: httpx's messages carry the URL and a paragraph of help."""
    if isinstance(error, httpx.HTTPStatusError):
        return f"HTTP {error.response.status_code}"
    if isinstance(error, httpx.HTTPError):
        return f"error de conexión ({type(error).__name__})"
    return str(error)


def _notify(on_file: FileEvent | None, event: str, remote: RemoteFile, local: Path) -> None:
    if on_file:
        on_file(event, remote, local)
