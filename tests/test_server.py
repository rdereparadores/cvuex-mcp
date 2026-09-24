"""End-to-end tests of the MCP tools through an in-memory MCP client."""

import pytest
from helpers import FakeMoodle, load_fixture
from mcp.client import Client

from cvuex_mcp import server
from cvuex_mcp.credentials import Credentials, CredentialStore
from cvuex_mcp.rate_limit import RateLimiter
from cvuex_mcp.state import PersistentState
from cvuex_mcp.storage import HOME_ENV_VAR

SITE_INFO = "core_webservice_get_site_info"


@pytest.fixture
def store(tmp_path, monkeypatch) -> CredentialStore:
    monkeypatch.setenv(HOME_ENV_VAR, str(tmp_path))
    return CredentialStore()


@pytest.fixture
def fake_moodle(monkeypatch) -> FakeMoodle:
    fake = FakeMoodle({SITE_INFO: load_fixture(SITE_INFO)})
    monkeypatch.setattr(server, "new_http_client", fake.http_client)
    monkeypatch.setattr(server, "RateLimiter", lambda: RateLimiter(min_interval=0))
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


COURSES = "core_course_get_enrolled_courses_by_timeline_classification"


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
    assert server.changes_since(saved, None, now=10 * WEEK) == 9 * WEEK  # first time: a week
    saved.set(server.LAST_CHANGES_CHECK, 123)
    assert server.changes_since(saved, None, now=10 * WEEK) == 123
    assert server.changes_since(saved, 2, now=10 * WEEK) == 10 * WEEK - 2 * 3600


async def test_novedades_remembers_the_last_full_check(store, fake_moodle):
    store.save("avuex", Credentials("tok"))
    fake_moodle.answers |= {
        COURSES: load_fixture(COURSES),
        UPDATES: {"instances": [], "warnings": []},
    }
    saved = PersistentState()

    await call("novedades")
    first_mark = saved.get(server.LAST_CHANGES_CHECK)
    assert first_mark is not None

    saved.set(server.LAST_CHANGES_CHECK, 1000)
    await call("novedades", {"desde_horas": 24})
    await call("novedades", {"asignatura_id": 32338})
    assert saved.get(server.LAST_CHANGES_CHECK) == 1000  # partial checks don't move it

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


async def test_instructions_mention_every_tool():
    async with Client(server.mcp) as client:
        tools = [tool.name for tool in (await client.list_tools()).tools]
    assert len(tools) == 6
    for tool in tools:
        assert tool in server.INSTRUCTIONS, tool
