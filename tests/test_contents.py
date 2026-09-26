import pytest
from helpers import COURSES, FakeMoodle, load_fixture

from cvuex_mcp.campus import Campus
from cvuex_mcp.campus import contents as contents_module
from cvuex_mcp.campus.contents import CourseNotAvailableError, course_contents
from cvuex_mcp.moodle import MoodleError

CONTENTS = "core_course_get_contents"
URL = "https://campusvirtual.unex.es/zonauex/avuex"


def campus_with_contents(fixture: str = f"{CONTENTS}__sintetico") -> tuple[Campus, FakeMoodle]:
    fake = FakeMoodle({COURSES: load_fixture(COURSES), CONTENTS: load_fixture(fixture)})
    return Campus(fake.client()), fake


async def test_real_course_with_labels_forum_and_choice():
    """Real data: the course page at the start of the term, still without materials."""
    campus, fake = campus_with_contents(CONTENTS)
    result = await course_contents(campus, 32254)

    assert result.url == f"{URL}/course/view.php?id=32254"
    assert [s.nombre for s in result.secciones] == [
        "Sistemas de Recomendación y Predicción (Máster Univ. en Ing. Informática)",
        "Evaluaciones y calificaciones",
        "Tema 1",
    ]
    label, forum, choice = result.secciones[0].elementos
    assert (label.tipo, label.url, label.ficheros) == ("texto", None, [])
    # Empty fields are left out: course pages can be long.
    assert forum.model_dump() == {
        "nombre": "Avisos",
        "tipo": "foro",
        "disponible": True,
        "url": f"{URL}/mod/forum/view.php?id=1823815",
    }
    assert choice.tipo == "consulta"
    assert result.secciones[2].elementos == []
    assert fake.calls[0]["courseid"] == "32254"


async def test_materials():
    campus, _ = campus_with_contents()
    result = await course_contents(campus, 32338)

    assert result.asignatura == "APRENDIZAJE AUTOMÁTICO Y APRENDIZAJE PROFUNDO"
    tema1 = result.secciones[1]
    assert (tema1.numero, tema1.nombre, tema1.resumen) == (
        1,
        "Tema 1",
        "Introducción a la materia.",
    )
    notes, folder, page, link, book, assignment, label = tema1.elementos

    assert notes.tipo == "archivo"
    assert notes.completado is True
    assert [f.model_dump() for f in notes.ficheros] == [
        {"nombre": "Tema1_Introduccion.pdf", "tamano": "2,3 MB", "fecha": "2026-09-22T18:00+02:00"}
    ]
    assert [f.nombre for f in folder.ficheros] == ["sesion1.pptx", "extra/sesion2.pdf"]
    assert (page.tipo, page.ficheros) == ("página", [])  # its text isn't a file to download
    assert (link.enlace, link.ficheros) == ("https://www.youtube.com/watch?v=abc123", [])
    assert (book.apartados, book.ficheros) == (["Introducción", "Conceptos básicos"], [])
    assert assignment.fechas == [
        "Apertura: 2026-09-21T18:00+02:00",
        "Entrega: 2026-10-01T18:00+02:00",
    ]
    assert assignment.completado is False
    assert label.descripcion == "Leed los apuntes antes de clase."


async def test_restricted_section_and_activity():
    campus, _ = campus_with_contents()
    tema2 = (await course_contents(campus, 32338)).secciones[2]
    assert not tema2.disponible
    assert tema2.restriccion == "No disponible hasta el 1 de octubre de 2026, 00:00"
    [quiz] = tema2.elementos
    assert (quiz.disponible, quiz.tipo) == (False, "cuestionario")
    assert quiz.restriccion == (
        "No disponible hasta que: la actividad Práctica 1 esté marcada como completada"
    )


async def test_subsections_are_shown_as_sections_inside_their_parent():
    campus, _ = campus_with_contents()
    result = await course_contents(campus, 32338)
    practicas = result.secciones[3]
    assert (practicas.nombre, practicas.dentro_de) == ("Prácticas", "Tema 1")
    assert [f.nombre for f in practicas.elementos[0].ficheros] == ["practica2.docx"]
    assert "subsección" not in {e.tipo for e in result.secciones[1].elementos}


async def test_one_section_with_its_subsections():
    campus, _ = campus_with_contents()
    result = await course_contents(campus, 32338, section=1)
    assert [s.nombre for s in result.secciones] == ["Tema 1", "Prácticas"]


async def test_folders_with_too_many_files(monkeypatch):
    monkeypatch.setattr(contents_module, "MAX_FILES_PER_ITEM", 1)
    campus, _ = campus_with_contents()
    result = await course_contents(campus, 32338)
    folder = result.secciones[1].elementos[1]
    assert len(folder.ficheros) == 1
    assert result.avisos == ["'Transparencias' tiene 2 ficheros; solo se muestran 1."]


@pytest.mark.parametrize("errorcode", ["invalidrecordunknown", "errorcoursecontextnotvalid"])
async def test_course_not_available(errorcode):
    """Real answers for a course that doesn't exist and for one the student isn't in."""
    campus, fake = campus_with_contents()
    fake.answers[CONTENTS] = {"exception": "x", "errorcode": errorcode, "message": "Error"}
    with pytest.raises(CourseNotAvailableError, match="asignatura 32000"):
        await course_contents(campus, 32000)


async def test_other_errors_are_not_hidden():
    campus, fake = campus_with_contents()
    fake.answers[CONTENTS] = {"exception": "x", "errorcode": "servererror", "message": "Boom"}
    with pytest.raises(MoodleError, match="Boom"):
        await course_contents(campus, 32338)
