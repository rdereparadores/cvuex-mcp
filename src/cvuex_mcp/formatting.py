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


# Moodle module names → how the Spanish UI calls them.
MODULE_TYPES = {
    "assign": "tarea",
    "quiz": "cuestionario",
    "forum": "foro",
    "choice": "consulta",
    "choicegroup": "elección de grupo",
    "workshop": "taller",
    "lesson": "lección",
    "feedback": "encuesta",
    "data": "base de datos",
    "glossary": "glosario",
    "wiki": "wiki",
    "scorm": "paquete SCORM",
    "h5pactivity": "H5P",
    "bigbluebuttonbn": "videoconferencia",
    "lti": "herramienta externa",
    "scheduler": "cita previa",
    "reservation": "reserva",
}


def module_type(module_name: str | None) -> str:
    return MODULE_TYPES.get(module_name or "", module_name or "otro")


# What changed in an activity, as reported by core_course_get_updates_since (Moodle 5.2).
# Names with a "user" prefix (usergrades...) mean the same as without it.
CHANGE_DESCRIPTIONS = {
    "configuration": "cambios en la actividad o su descripción",
    "contentfiles": "ficheros nuevos o modificados",
    "introfiles": "ficheros de la descripción modificados",
    "completion": "cambio en el estado de finalización",
    "gradeitems": "cambios en la calificación",
    "outcomes": "cambios en los resultados de aprendizaje",
    "comments": "comentarios nuevos",
    "ratings": "valoraciones nuevas",
    "discussions": "debates nuevos o con respuestas nuevas",
    "submissions": "cambios en las entregas",
    "grades": "calificaciones nuevas o modificadas",
    "attempts": "intentos nuevos o modificados",
    "questions": "preguntas modificadas",
    "answers": "respuestas nuevas",
    "entries": "entradas nuevas o modificadas",
    "pages": "páginas nuevas o modificadas",
    "tracks": "progreso registrado",
    "assessments": "evaluaciones nuevas",
    "assessmentgrades": "notas de evaluaciones nuevas",
    "attemptsfinished": "respuestas enviadas",
    "attemptsunfinished": "respuestas sin terminar",
}


def describe_change(name: str, item_count: int = 0) -> str:
    description = CHANGE_DESCRIPTIONS.get(name.removeprefix("user"), name)
    return f"{description} ({item_count})" if item_count else description


def component_origin(component: str | None) -> str:
    """Where a notification comes from: ``mod_forum`` → ``foro``; core ones → ``campus``."""
    if component and component.startswith("mod_"):
        return module_type(component.removeprefix("mod_"))
    return "campus"


# Calendar events not tied to an activity, by Moodle event type.
EVENT_KINDS = {
    "course": "evento de la asignatura",
    "group": "evento de grupo",
    "user": "evento personal",
    "site": "evento del campus",
    "category": "evento de la titulación",
}


def event_kind(event_type: str, module_name: str | None) -> str:
    """``("due", "assign")`` → ``tarea``; ``("course", None)`` → ``evento de la asignatura``."""
    if module_name:
        return module_type(module_name)
    return EVENT_KINDS.get(event_type, "evento")


def calendar_day_url(site: Site, course_id: int, timestamp: int, event_id: int) -> str:
    """Link to an event in the day view of Moodle's calendar."""
    query = f"view=day&course={course_id}&time={timestamp}"
    return f"{site.url}/calendar/view.php?{query}#event_{event_id}"


def short_text(html: str | None, max_chars: int = 300) -> str | None:
    """HTML → plain text cut to ``max_chars``, or None when there is no text."""
    text = html_to_text(html)
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "…"
    return text or None
