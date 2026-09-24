"""Turning Moodle data into compact, readable values for the assistant."""

import re
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

from cvuex_mcp.sites import Site

CAMPUS_TIMEZONE = ZoneInfo("Europe/Madrid")

_LINE_BREAK_TAGS = {"br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}


def iso_datetime(timestamp: int | None) -> str | None:
    """Unix timestamp → ISO 8601 in Spanish time. Moodle uses 0 for "no date"."""
    if not timestamp:
        return None
    return datetime.fromtimestamp(timestamp, CAMPUS_TIMEZONE).isoformat(timespec="minutes")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, _attrs) -> None:
        if tag in _LINE_BREAK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _LINE_BREAK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def html_to_text(html: str | None) -> str:
    """Strip tags, keeping paragraphs and line breaks as newlines."""
    if not html:
        return ""
    extractor = _TextExtractor()
    extractor.feed(html)
    extractor.close()
    text = unescape("".join(extractor.parts)).replace("\xa0", " ")
    lines = (re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def course_url(site: Site, course_id: int) -> str:
    return f"{site.url}/course/view.php?id={course_id}"


def module_url(site: Site, module_name: str, course_module_id: int) -> str:
    """Link to an activity, e.g. ``module_url(site, "assign", 123)``."""
    return f"{site.url}/mod/{module_name}/view.php?id={course_module_id}"
