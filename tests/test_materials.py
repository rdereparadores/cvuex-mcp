import asyncio
import os
import time
from pathlib import Path
from urllib.parse import urlparse

import pytest
from helpers import COURSES, FakeMoodle, campus_files, load_fixture, make_pdf

from cvuex_mcp.campus import Campus, CourseNotEnrolledError
from cvuex_mcp.jobs import BackgroundJob
from cvuex_mcp.materials import catalog as catalog_module
from cvuex_mcp.materials import sync as sync_module
from cvuex_mcp.materials.catalog import course_catalog
from cvuex_mcp.materials.index import MaterialsIndex
from cvuex_mcp.materials.layout import numbered, safe_name, section_folder
from cvuex_mcp.materials.lock import STALE_AFTER_SECONDS, SyncLock, SyncLockedError
from cvuex_mcp.materials.manifest import Manifest
from cvuex_mcp.materials.sync import SyncProgress, synchronize
from cvuex_mcp.moodle import InvalidTokenError

CONTENTS = "core_course_get_contents"
COURSE = "APRENDIZAJE AUTOMÁTICO Y APRENDIZAJE PROFUNDO"
URL = "https://campusvirtual.unex.es/zonauex/avuex"


class Setup:
    """A fake campus with the synthetic course, and a sync writing to a temporary folder."""

    def __init__(self, tmp_path: Path, contents: list | None = None) -> None:
        self.contents = contents or load_fixture(f"{CONTENTS}__sintetico")
        self.fake = FakeMoodle(
            {COURSES: load_fixture(COURSES), CONTENTS: lambda _form: self.contents},
            files=campus_files(self.contents),
        )
        self.root = tmp_path / "CVUEx"
        self.app = tmp_path / "app"
        self.campus = Campus(self.fake.client())

    async def sync(self, course_id: int | None = 32338, token: str = "tok") -> SyncProgress:
        progress = SyncProgress()
        await synchronize(
            self.campus,
            self.fake.client(token),
            course_id,
            progress,
            root=self.root,
            manifest_path=self.app / "materiales.sqlite",
            lock_path=self.app / "sincronizacion.lock",
        )
        return progress

    def local(self, path: str) -> Path:
        return self.root / COURSE / path

    def module_file(self, module_id: int) -> dict:
        return next(
            content
            for section in self.contents
            for module in section["modules"]
            if module["id"] == module_id
            for content in module["contents"]
        )


@pytest.fixture
def setup(tmp_path) -> Setup:
    return Setup(tmp_path)


# --- Names --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "safe"),
    [
        ("Tema 1: Introducción", "Tema 1_ Introducción"),
        ('a/b\\c<d>e"f|g?h*i', "a_b_c_d_e_f_g_h_i"),
        ("Apuntes. ", "Apuntes"),
        ("..", "_"),
        ("CON.txt", "_CON.txt"),
        ("con", "_con"),
        ("  varios   espacios  ", "varios espacios"),
    ],
)
def test_safe_names(name, safe):
    assert safe_name(name) == safe


def test_long_names_keep_their_extension():
    name = safe_name("x" * 300 + ".pdf")
    assert len(name) == 100
    assert name.endswith("xxx.pdf")


def test_section_folders_and_numbered_copies():
    assert section_folder(3, "Tema 2") == "03 - Tema 2"
    assert numbered("notas.pdf", 2) == "notas (2).pdf"
    assert numbered("LEEME", 3) == "LEEME (3)"


# --- Catalog ------------------------------------------------------------------


async def test_catalog(setup):
    catalog = await course_catalog(setup.campus, 32338)
    assert [(str(f.path), f.kind) for f in catalog.files] == [
        ("01 - Tema 1/Tema1_Introduccion.pdf", "fichero"),
        ("01 - Tema 1/Transparencias/sesion1.pptx", "fichero"),
        ("01 - Tema 1/Transparencias/extra/sesion2.pdf", "fichero"),
        ("01 - Tema 1/Guía de estudio.html", "página"),  # not the page's image
        ("01 - Tema 1/Manual de la asignatura/01 - Introducción.html", "capítulo"),
        ("01 - Tema 1/Manual de la asignatura/02 - Conceptos básicos.html", "capítulo"),
        ("03 - Prácticas/practica2.docx", "fichero"),
    ]
    notes = catalog.files[0]
    assert (notes.section, notes.module, notes.size) == ("Tema 1", "Apuntes del tema 1", 2_400_000)
    assert notes.module_url == f"{URL}/mod/resource/view.php?id=1900001"
    assert catalog.too_big == []


async def test_catalog_leaves_out_big_and_junk_files(setup, monkeypatch):
    monkeypatch.setattr(catalog_module, "MAX_FILE_BYTES", 1_000_000)
    folder = setup.contents[1]["modules"][1]
    junk = dict(folder["contents"][0], filename="._sesion1.pptx", filepath="/__MACOSX/")
    ds_store = dict(folder["contents"][0], filename=".DS_Store")
    folder["contents"] += [junk, ds_store]

    catalog = await course_catalog(setup.campus, 32338)
    assert {f.path.name for f in catalog.too_big} == {"Tema1_Introduccion.pdf", "sesion1.pptx"}
    assert "._sesion1.pptx" not in {f.path.name for f in catalog.files + catalog.too_big}
    assert ".DS_Store" not in {f.path.name for f in catalog.files + catalog.too_big}


async def test_files_with_the_same_name_are_numbered(setup):
    tema1 = setup.contents[1]["modules"]
    tema1.append(dict(tema1[0], id=1900099, name="Otra copia"))
    tema1[-1]["contents"] = [dict(tema1[0]["contents"][0], filename="tema1_introduccion.PDF")]
    catalog = await course_catalog(setup.campus, 32338)
    assert "01 - Tema 1/tema1_introduccion (2).PDF" in {str(f.path) for f in catalog.files}


# --- Sync ---------------------------------------------------------------------


async def test_first_sync_downloads_everything(setup):
    progress = await setup.sync()

    assert (progress.found, progress.downloaded, progress.up_to_date) == (7, 7, 0)
    assert progress.courses == [COURSE]
    assert setup.local("01 - Tema 1/Tema1_Introduccion.pdf").read_bytes() == (
        b"contenido de Tema1_Introduccion.pdf"
    )
    assert setup.local("01 - Tema 1/Guía de estudio.html").read_bytes() == (
        b"contenido de index.html"
    )
    entries = Manifest(setup.app / "materiales.sqlite").files(32338)
    assert len(entries) == 7
    assert entries[0].path.startswith(f"{COURSE}/")


async def test_the_token_goes_in_the_body_never_in_the_url(setup):
    await setup.sync()
    assert setup.fake.downloads
    for request in setup.fake.downloads:
        assert request.method == "POST"
        assert "tok" not in str(request.url)
        assert b"token=tok" in request.content


async def test_second_sync_only_downloads_what_changed(setup):
    await setup.sync()
    setup.fake.downloads.clear()
    setup.module_file(1900001)["timemodified"] += 60  # the teacher uploads a new version

    progress = await setup.sync()
    assert (progress.downloaded, progress.up_to_date) == (1, 6)
    assert [urlparse(str(r.url)).path.rsplit("/", 1)[-1] for r in setup.fake.downloads] == [
        "Tema1_Introduccion.pdf"
    ]


async def test_files_deleted_by_the_student_are_downloaded_again(setup):
    await setup.sync()
    setup.local("03 - Prácticas/practica2.docx").unlink()
    progress = await setup.sync()
    assert progress.downloaded == 1
    assert setup.local("03 - Prácticas/practica2.docx").exists()


async def test_files_removed_from_the_campus_are_kept(setup):
    await setup.sync()
    setup.contents[3]["modules"] = []  # the teacher removes the practice
    progress = await setup.sync()
    assert progress.removed == 1
    assert setup.local("03 - Prácticas/practica2.docx").exists()
    [entry] = [e for e in Manifest(setup.app / "materiales.sqlite").files() if not e.in_campus]
    assert entry.path.endswith("practica2.docx")


async def test_the_students_own_files_are_never_overwritten(setup):
    mine = setup.local("01 - Tema 1/Tema1_Introduccion.pdf")
    mine.parent.mkdir(parents=True)
    mine.write_bytes(b"mis notas")

    await setup.sync()
    assert mine.read_bytes() == b"mis notas"
    assert setup.local("01 - Tema 1/Tema1_Introduccion (2).pdf").exists()


async def test_a_failed_download_does_not_stop_the_rest(setup):
    del setup.fake.files["/2900009/mod_resource/content/0/practica2.docx"]
    progress = await setup.sync()
    assert progress.downloaded == 6
    [warning] = [w for w in progress.warnings if w.startswith("No se pudo descargar")]
    assert warning == (
        f"No se pudo descargar {COURSE}/03 - Prácticas/practica2.docx: El archivo no se encuentra"
    )


async def test_an_expired_session_stops_the_sync(setup):
    with pytest.raises(InvalidTokenError):
        await setup.sync(token="caducado")


async def test_only_enrolled_courses(setup):
    with pytest.raises(CourseNotEnrolledError, match="asignatura 99"):
        await setup.sync(course_id=99)


async def test_only_one_sync_at_a_time(setup):
    with SyncLock(setup.app / "sincronizacion.lock"), pytest.raises(SyncLockedError):
        await setup.sync()


def test_a_lock_left_by_a_crash_expires(tmp_path):
    path = tmp_path / "sincronizacion.lock"
    path.touch()
    old = time.time() - STALE_AFTER_SECONDS - 1
    os.utime(path, (old, old))
    with SyncLock(path):
        assert path.exists()
    assert not path.exists()


async def test_sync_indexes_the_text_once(setup):
    notes = "/2900001/mod_resource/content/0/Tema1_Introduccion.pdf"
    setup.fake.files[notes] = make_pdf(["Introducción a las redes neuronales", "El perceptrón"])

    first = await setup.sync()
    index = MaterialsIndex(setup.app / "materiales.sqlite")
    matches, _ = index.search("perceptron")
    assert [(m.document.path, m.number) for m in matches] == [
        (f"{COURSE}/01 - Tema 1/Tema1_Introduccion.pdf", 2)
    ]
    assert first.indexed >= 1  # also the pages and chapters (HTML) and text files

    second = await setup.sync()
    assert second.indexed == 0  # nothing changed: nothing is read again
    index.close()


async def test_a_new_extraction_reads_every_document_again(setup, monkeypatch):
    await setup.sync()
    monkeypatch.setattr(sync_module, "EXTRACTION_VERSION", 999)
    assert (await setup.sync()).indexed >= 1


async def test_documents_without_text_are_reported(setup):
    notes = "/2900001/mod_resource/content/0/Tema1_Introduccion.pdf"
    setup.fake.files[notes] = make_pdf(["", ""])
    progress = await setup.sync()
    assert progress.not_searchable == [
        f"{COURSE}/01 - Tema 1/Tema1_Introduccion.pdf: no tiene texto (quizá es un PDF escaneado)"
    ]


# --- Download -----------------------------------------------------------------


async def test_downloads_only_from_the_campus(tmp_path):
    client = FakeMoodle({}).client()
    with pytest.raises(ValueError, match="No es un fichero"):
        await client.download("https://example.com/webservice/pluginfile.php/1/a.pdf", tmp_path)


async def test_a_json_file_is_not_mistaken_for_an_error(tmp_path):
    fake = FakeMoodle({}, files={"/1/mod_resource/content/0/datos.json": b'{"a": 1}'})
    target = tmp_path / "datos.json"
    size = await fake.client().download(
        f"{URL}/webservice/pluginfile.php/1/mod_resource/content/0/datos.json", target
    )
    assert (size, target.read_bytes()) == (8, b'{"a": 1}')


async def test_failed_downloads_leave_no_files(tmp_path):
    with pytest.raises(InvalidTokenError):
        await (
            FakeMoodle({})
            .client("caducado")
            .download(f"{URL}/webservice/pluginfile.php/1/x.pdf", tmp_path / "x.pdf")
        )
    assert list(tmp_path.iterdir()) == []


# --- Background ---------------------------------------------------------------


async def test_background_sync_reports_while_running_and_keeps_errors():
    job = BackgroundJob()
    release = asyncio.Event()

    async def slow(progress: SyncProgress) -> None:
        progress.found = 3
        await release.wait()
        raise InvalidTokenError("invalidtoken", "caducado")

    progress = job.start(slow, SyncProgress())
    await job.wait(0.01)
    assert job.running
    assert progress.found == 3

    release.set()
    await job.wait(1)
    assert not job.running
    assert "cvuex-mcp login" in progress.error
    assert progress.finished_at is not None
