import pytest

from cvuex_mcp.formatting import course_url, html_to_text, iso_datetime, module_url
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
