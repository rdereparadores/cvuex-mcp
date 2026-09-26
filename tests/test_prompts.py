import re

import pytest
from mcp.client import Client

from cvuex_mcp import server

# Words in the prompts that look like tool names but are parameters.
PARAMETERS = {"asignatura_id"}


async def list_prompts():
    async with Client(server.mcp) as client:
        return (await client.list_prompts()).prompts


async def get_prompt(name: str, arguments: dict | None = None) -> str:
    async with Client(server.mcp) as client:
        result = await client.get_prompt(name, arguments or {})
    [message] = result.messages
    assert message.role == "user"
    return message.content.text


async def test_prompts_and_their_arguments():
    prompts = {prompt.name: prompt for prompt in await list_prompts()}
    assert set(prompts) == {"resumen_semanal", "preparar_examen", "ponerme_al_dia"}
    assert all(prompt.description for prompt in prompts.values())
    assert [(a.name, a.required) for a in prompts["preparar_examen"].arguments] == [
        ("asignatura", True),
        ("tema", False),
    ]
    assert [a.name for a in prompts["ponerme_al_dia"].arguments] == ["asignatura"]
    assert prompts["resumen_semanal"].arguments in (None, [])


async def test_prepare_an_exam_with_or_without_a_topic():
    text = await get_prompt("preparar_examen", {"asignatura": "Redes", "tema": "Tema 3"})
    assert "el tema «Tema 3» de Redes" in text
    assert "Cita siempre el documento y la página" in text
    whole = await get_prompt("preparar_examen", {"asignatura": "Redes"})
    assert "toda la asignatura Redes" in whole


async def test_catch_up_names_the_course():
    assert (await get_prompt("ponerme_al_dia", {"asignatura": "DISI"})).startswith(
        "Ponme al día de DISI."
    )


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("resumen_semanal", {}),
        ("preparar_examen", {"asignatura": "Redes"}),
        ("ponerme_al_dia", {"asignatura": "Redes"}),
    ],
)
async def test_prompts_only_mention_tools_that_exist(name, arguments):
    async with Client(server.mcp) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
    text = await get_prompt(name, arguments)
    mentioned = set(re.findall(r"\b[a-z]+(?:_[a-z]+)+\b", text)) - PARAMETERS
    assert mentioned
    assert mentioned <= tools, mentioned - tools
