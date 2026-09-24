import pytest

from cvuex_mcp.formatting import (
    component_origin,
    course_url,
    describe_change,
    event_kind,
    html_to_text,
    iso_datetime,
    module_url,
    short_text,
)
from cvuex_mcp.sites import AVUEX


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        (1790546400, "2026-09-28T00:00+02:00"),  # summer time
        (1795820400, "2026-11-28T00:00+01:00"),  # winter time
        (0, None),
        (None, None),
    ],
)
def test_iso_datetime_uses_spanish_time(timestamp, expected):
    assert iso_datetime(timestamp) == expected


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        ("<p>Hola&nbsp;<b>mundo</b></p><p>Adiós</p>", "Hola mundo\n\nAdiós"),
        ("línea 1<br>línea 2", "línea 1\nlínea 2"),
        ("<ul><li>uno</li><li>dos</li></ul>", "uno\n\ndos"),
        ('<div class="no-overflow"><p><img src="x.png" alt="imagen"></p></div>', ""),
        ("&lt;código&gt; &amp; más", "<código> & más"),
        ("", ""),
        (None, ""),
    ],
)
def test_html_to_text(html, expected):
    assert html_to_text(html) == expected


def test_campus_urls():
    assert course_url(AVUEX, 32254) == f"{AVUEX.url}/course/view.php?id=32254"
    assert module_url(AVUEX, "forum", 1823815) == f"{AVUEX.url}/mod/forum/view.php?id=1823815"


@pytest.mark.parametrize(
    ("name", "count", "expected"),
    [
        ("discussions", 2, "debates nuevos o con respuestas nuevas (2)"),
        ("usergrades", 0, "calificaciones nuevas o modificadas"),
        ("desconocido", 0, "desconocido"),
    ],
)
def test_describe_change(name, count, expected):
    assert describe_change(name, count) == expected


@pytest.mark.parametrize(
    ("component", "expected"),
    [("mod_forum", "foro"), ("mod_assign", "tarea"), ("moodle", "campus"), (None, "campus")],
)
def test_component_origin(component, expected):
    assert component_origin(component) == expected


@pytest.mark.parametrize(
    ("event_type", "module_name", "expected"),
    [
        ("open", "choice", "consulta"),
        ("course", None, "evento de la asignatura"),
        ("x", None, "evento"),
    ],
)
def test_event_kind(event_type, module_name, expected):
    assert event_kind(event_type, module_name) == expected


def test_short_text():
    assert short_text("<p>hola</p>") == "hola"
    assert short_text("<p></p>") is None
    assert short_text("a" * 10, max_chars=4) == "aaaa…"
