"""End-to-end tests of the MCP tools through an in-memory MCP client."""

import asyncio
import time

import pytest
from helpers import COURSES, FakeMoodle, campus_files, load_fixture, make_pdf
from mcp.client import Client

from cvuex_mcp import runtime, server
from cvuex_mcp.credentials import Credentials, CredentialStore
from cvuex_mcp.rate_limit import RateLimiter
from cvuex_mcp.state import PersistentState
from cvuex_mcp.storage import HOME_ENV_VAR, MATERIALS_ENV_VAR
from cvuex_mcp.tools import changes as changes_tool
from cvuex_mcp.tools import materials as materials_tool

SITE_INFO = "core_webservice_get_site_info"
NO_DISCUSSIONS = {"discussions": [], "warnings": []}
COURSES_32338 = "APRENDIZAJE AUTOMÁTICO Y APRENDIZAJE PROFUNDO"


@pytest.fixture
def store(tmp_path, monkeypatch) -> CredentialStore:
    monkeypatch.setenv(HOME_ENV_VAR, str(tmp_path))
    return CredentialStore()


@pytest.fixture
def fake_moodle(monkeypatch) -> FakeMoodle:
    fake = FakeMoodle({SITE_INFO: load_fixture(SITE_INFO)})
    monkeypatch.setattr(runtime, "new_http_client", fake.http_client)
    monkeypatch.setattr(runtime, "RateLimiter", lambda: RateLimiter(min_interval=0))
    return fake


async def call(tool: str, arguments: dict | None = None):
    async with Client(server.mcp) as client:
        return await client.call_tool(tool, arguments or {})


async def test_quien_soy(store, fake_moodle):
    store.save("avuex", Credentials("tok"))
    result = await call("quien_soy")
    assert result.structured_content == {
        "nombre": "Persona 4",
        "usuario": "Persona 1",
        "plataforma": "Aulas regladas (AVUEx)",
    }


async def test_without_session_explains_how_to_log_in(store, fake_moodle):
    result = await call("quien_soy")
    assert result.is_error
    assert "cvuex-mcp login" in result.content[0].text
    assert fake_moodle.calls == []


async def test_expired_session_explains_how_to_log_in(store, fake_moodle):
    store.save("avuex", Credentials("old"))
    fake_moodle.answers[SITE_INFO] = {"exception": "x", "errorcode": "invalidtoken", "message": ""}
    result = await call("quien_soy")
    assert result.is_error
    assert "ha caducado" in result.content[0].text


async def test_new_login_is_used_without_restarting(store, fake_moodle):
    store.save("avuex", Credentials("first"))
    async with Client(server.mcp) as client:
        await client.call_tool("quien_soy", {})
        await client.call_tool("quien_soy", {})  # answered from the cache
        store.save("avuex", Credentials("second"))
        await client.call_tool("quien_soy", {})

    assert [call["wstoken"] for call in fake_moodle.calls] == ["first", "second"]


async def test_mis_asignaturas(store, fake_moodle):
    store.save("avuex", Credentials("tok"))
    fake_moodle.answers[COURSES] = load_fixture(COURSES)

    result = await call("mis_asignaturas", {"estado": "todas"})

    courses = result.structured_content["asignaturas"]
    assert [course["nombre"] for course in courses] == [
        "APRENDIZAJE AUTOMÁTICO Y APRENDIZAJE PROFUNDO",
        "COMPUTACIÓN GRÁFICA",
        "NORMATIVA, LEGISLACIÓN Y REGULACIÓN INFORMÁTICA",
    ]
    assert fake_moodle.calls[0]["classification"] == "all"


async def test_mis_asignaturas_defaults_to_current_courses(store, fake_moodle):
    store.save("avuex", Credentials("tok"))
    fake_moodle.answers[COURSES] = load_fixture(COURSES)
    await call("mis_asignaturas")
    assert fake_moodle.calls[0]["classification"] == "inprogress"


async def test_mis_asignaturas_rejects_unknown_state(store, fake_moodle):
    store.save("avuex", Credentials("tok"))
    result = await call("mis_asignaturas", {"estado": "inventado"})
    assert result.is_error
    assert fake_moodle.calls == []


BY_TIMESORT = "core_calendar_get_action_events_by_timesort"


async def test_proximos_plazos(store, fake_moodle):
    store.save("avuex", Credentials("tok"))
    fake_moodle.answers |= {
        BY_TIMESORT: load_fixture(f"{BY_TIMESORT}__sintetico"),
        "core_calendar_get_calendar_events": {"events": [], "warnings": []},
        COURSES: load_fixture(COURSES),
    }

    result = await call("proximos_plazos", {"dias": 7})

    assert not result.is_error
    deadlines = result.structured_content["plazos"]
    assert [d["actividad"] for d in deadlines] == [
        "Práctica 0",
        "Práctica 1: regresión lineal",
        "Cuestionario tema 1",
    ]


@pytest.mark.parametrize("dias", [0, 91])
async def test_proximos_plazos_rejects_out_of_range_days(store, fake_moodle, dias):
    store.save("avuex", Credentials("tok"))
    result = await call("proximos_plazos", {"dias": dias})
    assert result.is_error
    assert fake_moodle.calls == []


ASSIGNMENTS = "mod_assign_get_assignments"
STATUS = "mod_assign_get_submission_status"


async def test_estado_entregas(store, fake_moodle):
    store.save("avuex", Credentials("tok"))
    statuses = load_fixture(f"{STATUS}__sintetico_por_tarea")
    fake_moodle.answers |= {
        ASSIGNMENTS: load_fixture(f"{ASSIGNMENTS}__sintetico"),
        STATUS: lambda form: statuses[form["assignid"]],
    }

    result = await call("estado_entregas", {"asignatura_id": 32338, "solo_pendientes": False})

    assert not result.is_error
    assert len(result.structured_content["entregas"]) == 4  # the fake ignores the course filter
    assert fake_moodle.calls[0]["courseids[0]"] == "32338"


UPDATES = "core_course_get_updates_since"
WEEK = 7 * 24 * 3600


def test_changes_since(tmp_path):
    saved = PersistentState(tmp_path / "state.json")
    assert changes_tool.changes_since(saved, None, now=10 * WEEK) == 9 * WEEK  # first time: a week
    saved.set(changes_tool.LAST_CHANGES_CHECK, 123)
    assert changes_tool.changes_since(saved, None, now=10 * WEEK) == 123
    assert changes_tool.changes_since(saved, 2, now=10 * WEEK) == 10 * WEEK - 2 * 3600


async def test_novedades_remembers_the_last_full_check(store, fake_moodle):
    store.save("avuex", Credentials("tok"))
    fake_moodle.answers |= {
        COURSES: load_fixture(COURSES),
        UPDATES: {"instances": [], "warnings": []},
    }
    saved = PersistentState()

    await call("novedades")
    first_mark = saved.get(changes_tool.LAST_CHANGES_CHECK)
    assert first_mark is not None

    saved.set(changes_tool.LAST_CHANGES_CHECK, 1000)
    await call("novedades", {"desde_horas": 24})
    await call("novedades", {"asignatura_id": 32338})
    assert saved.get(changes_tool.LAST_CHANGES_CHECK) == 1000  # partial checks don't move it

    fake_moodle.calls.clear()
    await call("novedades")
    assert {c["since"] for c in fake_moodle.calls if c["wsfunction"] == UPDATES} == {"1000"}


NOTIFICATIONS = "message_popup_get_popup_notifications"


async def test_notificaciones(store, fake_moodle):
    store.save("avuex", Credentials("tok"))
    fake_moodle.answers[NOTIFICATIONS] = load_fixture(f"{NOTIFICATIONS}__sintetico")

    result = await call("notificaciones")

    assert result.structured_content["sin_leer"] == 2
    assert len(result.structured_content["notificaciones"]) == 2


async def test_notificaciones_rejects_invalid_limit(store, fake_moodle):
    store.save("avuex", Credentials("tok"))
    result = await call("notificaciones", {"limite": 0})
    assert result.is_error
    assert fake_moodle.calls == []


FORUMS = "mod_forum_get_forums_by_courses"
DISCUSSIONS = "mod_forum_get_forum_discussions"
POSTS = "mod_forum_get_discussion_posts"


async def test_avisos_and_leer_debate(store, fake_moodle):
    store.save("avuex", Credentials("tok"))
    discussions = load_fixture(DISCUSSIONS)
    discussions["discussions"][0]["timemodified"] = int(time.time()) - 3600
    fake_moodle.answers |= {
        COURSES: load_fixture(COURSES),
        FORUMS: load_fixture(FORUMS),
        DISCUSSIONS: lambda form: discussions if form["forumid"] == "72401" else NO_DISCUSSIONS,
        POSTS: load_fixture(POSTS),
    }

    [announcement] = (await call("avisos")).structured_content["avisos"]
    assert announcement["foro"] == "Foro general de la asignatura"

    result = await call("leer_debate", {"debate_id": announcement["debate_id"]})
    assert result.structured_content["titulo"] == announcement["titulo"]
    assert len(result.structured_content["mensajes"]) == 1


GRADE_ITEMS = "gradereport_user_get_grade_items"


async def test_calificaciones(store, fake_moodle):
    store.save("avuex", Credentials("tok"))
    fake_moodle.answers |= {
        COURSES: load_fixture(COURSES),
        GRADE_ITEMS: load_fixture(f"{GRADE_ITEMS}__sintetico"),
        "core_grades_get_gradeitems": load_fixture("core_grades_get_gradeitems__sintetico"),
    }
    result = (await call("calificaciones", {"asignatura_id": 32338})).structured_content
    assert result["asignaturas"][0]["nota"] == "7,40"
    assert len(result["detalle"]) == 7


QUIZZES = "mod_quiz_get_quizzes_by_courses"
ATTEMPTS = "mod_quiz_get_user_quiz_attempts"
REVIEW = "mod_quiz_get_attempt_review"


async def test_cuestionarios_and_revisar_cuestionario(store, fake_moodle):
    store.save("avuex", Credentials("tok"))
    fake_moodle.answers |= {
        COURSES: load_fixture(COURSES),
        QUIZZES: load_fixture(f"{QUIZZES}__sintetico"),
        ATTEMPTS: load_fixture(f"{ATTEMPTS}__sintetico"),
        REVIEW: load_fixture(f"{REVIEW}__sintetico"),
    }
    result = (await call("cuestionarios")).structured_content
    [attempt_id] = {
        attempt["intento_id"]
        for quiz in result["cuestionarios"]
        if quiz["cuestionario"] == "Test tema 1"
        for attempt in quiz["intentos"][:1]
    }

    review = (await call("revisar_cuestionario", {"intento_id": attempt_id})).structured_content
    assert review["nota"] == 6.0
    assert len(review["preguntas"]) == 5


async def test_revisar_cuestionario_refuses_attempts_in_progress(store, fake_moodle):
    store.save("avuex", Credentials("tok"))
    fake_moodle.answers[REVIEW] = {
        "exception": "moodle_exception",
        "errorcode": "attemptclosed",
        "message": "Este intento ya está cerrado",
    }
    result = await call("revisar_cuestionario", {"intento_id": 5003})
    assert result.is_error
    assert "no está terminado" in result.content[0].text


async def test_contenido_asignatura(store, fake_moodle):
    store.save("avuex", Credentials("tok"))
    fake_moodle.answers |= {
        COURSES: load_fixture(COURSES),
        "core_course_get_contents": load_fixture("core_course_get_contents__sintetico"),
    }
    result = await call("contenido_asignatura", {"asignatura_id": 32338, "seccion": 1})
    assert not result.is_error  # the client checks the answer against the tool's schema
    sections = result.structured_content["secciones"]
    assert [s["nombre"] for s in sections] == ["Tema 1", "Prácticas"]
    notes = sections[0]["elementos"][0]
    assert "enlace" not in notes  # empty fields are left out
    assert ": null" not in result.content[0].text
    assert ": []" not in result.content[0].text


async def test_contenido_asignatura_of_a_course_not_enrolled(store, fake_moodle):
    store.save("avuex", Credentials("tok"))
    fake_moodle.answers["core_course_get_contents"] = {
        "exception": "x",
        "errorcode": "errorcoursecontextnotvalid",
        "message": "Curso o actividad no accesible.",
    }
    result = await call("contenido_asignatura", {"asignatura_id": 32000})
    assert result.is_error
    assert "Usa un id de los que da mis_asignaturas" in result.content[0].text


async def test_contacto_profesorado(store, fake_moodle):
    store.save("avuex", Credentials("tok"))
    fake_moodle.answers |= {
        COURSES: load_fixture(COURSES),
        "core_course_get_courses_by_field": load_fixture("core_course_get_courses_by_field"),
        "core_user_get_users_by_field": load_fixture("core_user_get_users_by_field"),
    }
    result = await call("contacto_profesorado", {"asignatura_id": 32338})
    assert not result.is_error  # the client checks the answer against the tool's schema
    [course] = result.structured_content["asignaturas"]
    assert [t["correo"] for t in course["profesores"]] == [
        "persona1@example.com",
        "persona2@example.com",
    ]


async def test_contacto_profesorado_of_a_course_not_enrolled(store, fake_moodle):
    store.save("avuex", Credentials("tok"))
    fake_moodle.answers[COURSES] = load_fixture(COURSES)
    result = await call("contacto_profesorado", {"asignatura_id": 32000})
    assert result.is_error
    assert "Usa un id de los que da mis_asignaturas" in result.content[0].text


async def test_exportar_calendario(store, fake_moodle, tmp_path, monkeypatch):
    store.save("avuex", Credentials("tok"))
    monkeypatch.setenv(MATERIALS_ENV_VAR, str(tmp_path / "CVUEx"))
    events = load_fixture("core_calendar_get_action_events_by_timesort__sintetico")
    fake_moodle.answers |= {
        COURSES: load_fixture(COURSES),
        "core_calendar_get_action_events_by_timesort": events,
        "core_calendar_get_calendar_events": {"events": []},
    }
    result = await call("exportar_calendario", {"dias": 30})
    assert not result.is_error  # the client checks the answer against the tool's schema
    exported = result.structured_content
    assert exported["fichero"] == str(tmp_path / "CVUEx" / "calendario.ics")
    assert "Google Calendar" in exported["como_importar"]
    assert (tmp_path / "CVUEx" / "calendario.ics").read_bytes().startswith(b"BEGIN:VCALENDAR")


@pytest.fixture
def course_materials(store, fake_moodle, tmp_path, monkeypatch):
    store.save("avuex", Credentials("tok"))
    monkeypatch.setenv(MATERIALS_ENV_VAR, str(tmp_path / "CVUEx"))
    contents = load_fixture("core_course_get_contents__sintetico")
    fake_moodle.answers |= {COURSES: load_fixture(COURSES), "core_course_get_contents": contents}
    fake_moodle.files = campus_files(contents)
    return tmp_path / "CVUEx"


async def test_sincronizar_materiales(course_materials):
    result = (await call("sincronizar_materiales", {"asignatura_id": 32338})).structured_content
    assert (result["estado"], result["descargados"], result["al_dia"]) == ("terminada", 7, 0)
    assert result["carpeta"] == str(course_materials)
    assert (course_materials / f"{COURSES_32338}/03 - Prácticas/practica2.docx").exists()

    again = (await call("sincronizar_materiales", {"asignatura_id": 32338})).structured_content
    assert (again["descargados"], again["al_dia"]) == (0, 7)


async def test_sincronizar_materiales_reports_a_sync_still_running(course_materials, monkeypatch):
    """A long sync goes on in the background, and is cancelled when the server stops."""
    cancelled = asyncio.Event()

    async def endless_sync(*_args, **_kwargs):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    monkeypatch.setattr(materials_tool, "synchronize", endless_sync)
    monkeypatch.setattr(materials_tool, "WAIT_SECONDS", 0.01)
    async with Client(server.mcp) as client:
        first = (await client.call_tool("sincronizar_materiales", {})).structured_content
        second = (await client.call_tool("sincronizar_materiales", {})).structured_content
    assert (first["estado"], second["estado"], second["fin"]) == ("en_curso", "en_curso", None)
    assert cancelled.is_set()


async def test_search_and_read_the_materials(course_materials, fake_moodle):
    notes = "/2900001/mod_resource/content/0/Tema1_Introduccion.pdf"
    fake_moodle.files[notes] = make_pdf(
        ["Tema 1: introducción a las redes neuronales", "El perceptrón multicapa aprende pesos"]
    )
    await call("sincronizar_materiales", {"asignatura_id": 32338})

    found = (await call("buscar_en_materiales", {"consulta": "perceptron"})).structured_content
    [match] = found["resultados"]
    assert (match["documento"], match["ubicacion"]) == ("Tema1_Introduccion.pdf", "página 2")

    arguments = {"documento_id": match["documento_id"], "desde": match["numero"]}
    text = (await call("leer_material", arguments)).structured_content
    assert text["texto"] == "[Página 2]\nEl perceptrón multicapa aprende pesos"


async def test_leer_material_explains_what_cannot_be_read(course_materials):
    result = await call("leer_material", {"documento_id": 99})
    assert result.is_error
    assert "buscar_en_materiales" in result.content[0].text


async def test_buscar_en_foros(store, fake_moodle):
    store.save("avuex", Credentials("tok"))
    fake_moodle.answers |= {
        COURSES: load_fixture(COURSES),
        FORUMS: load_fixture(FORUMS),
        DISCUSSIONS: lambda form: (
            load_fixture(DISCUSSIONS) if form["forumid"] == "72401" else NO_DISCUSSIONS
        ),
    }
    result = (await call("buscar_en_foros", {"consulta": "videoconferencia"})).structured_content
    [match] = result["resultados"]
    assert (match["debate_id"], match["foro"]) == (41804, "Foro general de la asignatura")
    assert result["indice_al_dia"]

    fake_moodle.calls.clear()
    await call("buscar_en_foros", {"consulta": "martes"})
    assert DISCUSSIONS not in fake_moodle.functions_called()  # refreshed less than 10 min ago


async def test_only_expected_tools_change_something():
    """Reading discussions may mark their posts as read, and syncing and exporting the
    calendar write the student's files; nothing else changes anything, and nothing is
    destructive."""
    async with Client(server.mcp) as client:
        tools = (await client.list_tools()).tools
    changing = {tool.name for tool in tools if not tool.annotations.read_only_hint}
    assert changing == {
        "leer_debate",
        "buscar_en_foros",
        "sincronizar_materiales",
        "exportar_calendario",
    }
    assert all(tool.annotations.destructive_hint is not True for tool in tools)


async def test_instructions_mention_every_tool():
    async with Client(server.mcp) as client:
        tools = [tool.name for tool in (await client.list_tools()).tools]
    assert len(tools) == 18
    for tool in tools:
        assert tool in server.INSTRUCTIONS, tool


async def test_leer_debate_with_unknown_id(store, fake_moodle):
    store.save("avuex", Credentials("tok"))
    fake_moodle.answers[POSTS] = {"exception": "Error", "message": "PHP error"}
    result = await call("leer_debate", {"debate_id": 1})
    assert result.is_error
    assert "Usa un debate_id de los que da avisos" in result.content[0].text
