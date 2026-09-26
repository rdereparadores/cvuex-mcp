"""What can be downloaded from a course, and where it goes in the local folder.

Inside a course's folder:

    03 - Tema 2/
        apuntes.pdf                  a resource with a single file
        Transparencias/…             a folder, or a resource with several files
        Guía de estudio.html         a page
        Manual/01 - Introducción.html   a book, one file per chapter

Images embedded in pages and books are left out: without rewriting the HTML
they are no use on their own.
"""

from collections.abc import Iterator
from dataclasses import dataclass, replace
from pathlib import PurePosixPath
from typing import Any

from cvuex_mcp.campus.core import Campus
from cvuex_mcp.materials.layout import numbered, safe_name, section_folder

MAX_FILE_BYTES = 100 * 1024 * 1024  # larger files are downloaded from the campus by hand
DOWNLOADED_MODULES = {"resource", "folder", "page", "book"}
PAGE_FILE = "index.html"  # the text of a page, and of each book chapter
# Operating system leftovers teachers upload by mistake (e.g. unzipped on a Mac).
JUNK_FILES = {".ds_store", "thumbs.db", "desktop.ini"}
JUNK_FOLDERS = {"__macosx"}


@dataclass(frozen=True)
class RemoteFile:
    key: str
    """Stable within the course: the course module id and the file's path in it."""
    path: PurePosixPath
    """Where it goes inside the course's folder."""
    section: str
    module: str
    module_url: str | None
    kind: str
    """"fichero", "página" or "capítulo"."""
    size: int
    timemodified: int
    file_url: str


@dataclass
class CourseCatalog:
    files: list[RemoteFile]
    too_big: list[RemoteFile]


async def course_catalog(campus: Campus, course_id: int) -> CourseCatalog:
    # Fresh: a file the teacher has just uploaded must be downloaded now.
    sections = await campus.call("core_course_get_contents", fresh=True, courseid=course_id)
    taken: set[str] = set()
    files, too_big = [], []
    for section in sections:
        folder = PurePosixPath(section_folder(section["section"], section["name"]))
        for module in section["modules"]:
            if module["modname"] not in DOWNLOADED_MODULES or not module.get("uservisible", True):
                continue
            for remote in _module_files(section["name"], folder, module):
                remote = _with_free_path(remote, taken)
                (too_big if remote.size > MAX_FILE_BYTES else files).append(remote)
    return CourseCatalog(files=files, too_big=too_big)


def _module_files(
    section: str, folder: PurePosixPath, module: dict[str, Any]
) -> Iterator[RemoteFile]:
    contents = [c for c in module.get("contents") or [] if c["type"] == "file" and not _is_junk(c)]
    name = safe_name(module["name"])

    def remote(content: dict[str, Any], path: PurePosixPath, kind: str) -> RemoteFile:
        return RemoteFile(
            key=f"{module['id']}{content['filepath'] or '/'}{content['filename']}",
            path=path,
            section=section,
            module=module["name"],
            module_url=module.get("url"),
            kind=kind,
            size=content.get("filesize") or 0,
            timemodified=content.get("timemodified") or 0,
            file_url=content["fileurl"],
        )

    match module["modname"]:
        case "page":
            for content in contents:
                if content["filename"] == PAGE_FILE and content["filepath"] == "/":
                    yield remote(content, folder / f"{name}.html", "página")
        case "book":
            chapters = [c for c in contents if c["filename"] == PAGE_FILE]
            for number, content in enumerate(chapters, start=1):
                title = safe_name(f"{number:02d} - {content.get('content') or 'Capítulo'}")
                yield remote(content, folder / name / f"{title}.html", "capítulo")
        case "resource" if len(contents) == 1:
            yield remote(contents[0], folder / safe_name(contents[0]["filename"]), "fichero")
        case _:  # folders, and resources with several files
            for content in contents:
                subfolders = [safe_name(p) for p in (content["filepath"] or "/").split("/") if p]
                path = folder.joinpath(name, *subfolders, safe_name(content["filename"]))
                yield remote(content, path, "fichero")


def _is_junk(content: dict[str, Any]) -> bool:
    name = content["filename"].casefold()
    folders = (content["filepath"] or "/").casefold().split("/")
    return name in JUNK_FILES or name.startswith("._") or not JUNK_FOLDERS.isdisjoint(folders)


def _with_free_path(remote: RemoteFile, taken: set[str]) -> RemoteFile:
    """Two files can't share a name, not even differing only in case (macOS, Windows)."""
    path, copy = remote.path, 1
    while str(path).casefold() in taken:
        copy += 1
        path = remote.path.with_name(numbered(remote.path.name, copy))
    taken.add(str(path).casefold())
    return remote if path == remote.path else replace(remote, path=path)
