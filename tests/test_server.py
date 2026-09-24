"""End-to-end tests of the MCP tools through an in-memory MCP client."""

import pytest
from helpers import FakeMoodle, load_fixture
from mcp.client import Client

from cvuex_mcp import server
from cvuex_mcp.credentials import HOME_ENV_VAR, Credentials, CredentialStore

SITE_INFO = "core_webservice_get_site_info"


@pytest.fixture
def store(tmp_path, monkeypatch) -> CredentialStore:
    monkeypatch.setenv(HOME_ENV_VAR, str(tmp_path))
    return CredentialStore()


@pytest.fixture
def fake_moodle(monkeypatch) -> FakeMoodle:
    fake = FakeMoodle({SITE_INFO: load_fixture(SITE_INFO)})
    monkeypatch.setattr(server, "new_http_client", fake.http_client)
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
