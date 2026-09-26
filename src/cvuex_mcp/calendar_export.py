"""The upcoming deadlines as an iCalendar (.ics) file, for Google Calendar, Outlook...

The file stays on the student's computer. Moodle's own subscription link is not
used: it gives access to the calendar without logging in, and a student who logs
in through SSO cannot revoke it.
"""

from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from icalendar import Calendar, Event

from cvuex_mcp.campus.core import Campus
from cvuex_mcp.campus.deadlines import DAY_SECONDS, DatedDeadline, dated_deadlines, this_minute
from cvuex_mcp.formatting import iso_datetime
from cvuex_mcp.models import CalendarioExportado, Plazo
from cvuex_mcp.sites import Site
from cvuex_mcp.storage import materials_dir, write_file

CALENDAR_FILE = "calendario.ics"
MAX_DAYS = 90
HOW_TO_IMPORT = (
    "Es una copia de los plazos de ahora: si cambian, hay que volver a exportarlo. "
    "Google Calendar: en calendar.google.com (desde el ordenador), Configuración > "
    "Importar y exportar > Importar. Outlook: Calendario > Agregar calendario > "
    "Cargar desde archivo."
)


def calendar_path() -> Path:
    return materials_dir() / CALENDAR_FILE


async def export_calendar(
    campus: Campus, days: int, course_id: int | None, path: Path | None = None
) -> CalendarioExportado:
    """Write what's coming up in the next ``days`` (nothing overdue) to an .ics file."""
    if course_id is not None:
        await campus.enrolled_courses(course_id)  # raises if not enrolled
    now = this_minute(campus)
    until = now + days * DAY_SECONDS
    deadlines = [
        deadline
        for deadline in await dated_deadlines(campus, now, until, course_id)
        if not deadline.plazo.vencido
    ]
    path = path or calendar_path()
    write_file(path, calendar_ics(campus.site, deadlines, now))
    return CalendarioExportado(
        fichero=str(path),
        eventos=len(deadlines),
        desde=iso_datetime(now),
        hasta=iso_datetime(until),
        como_importar=HOW_TO_IMPORT,
    )


def calendar_ics(site: Site, deadlines: list[DatedDeadline], now: int) -> bytes:
    calendar = Calendar()
    calendar.add("prodid", "-//cvuex-mcp//Campus Virtual UEx//ES")
    calendar.add("version", "2.0")
    calendar.add("x-wr-calname", "Campus Virtual UEx")
    address = urlsplit(site.url)
    for deadline in deadlines:
        event = Event()
        # The UID of Moodle's own export ("<id>@<site without https://>").
        event.add("uid", f"{deadline.event_id}@{address.netloc}{address.path}")
        event.add("dtstamp", _utc(now))
        event.add("dtstart", _utc(deadline.start))
        event.add("dtend", _utc(deadline.start + deadline.duration))
        event.add("summary", _title(deadline.plazo))
        event.add("description", _description(deadline.plazo))
        event.add("url", deadline.plazo.url)
        calendar.add_component(event)
    return calendar.to_ical()


def _utc(timestamp: int) -> datetime:
    return datetime.fromtimestamp(timestamp, UTC)


def _title(plazo: Plazo) -> str:
    return f"{plazo.evento} ({plazo.asignatura})" if plazo.asignatura else plazo.evento


def _description(plazo: Plazo) -> str:
    lines = [
        f"Asignatura: {plazo.asignatura}" if plazo.asignatura else None,
        f"Tipo: {plazo.tipo}",
        f"Qué hacer: {plazo.accion}" if plazo.accion else None,
        plazo.descripcion,
        plazo.url,
    ]
    return "\n".join(line for line in lines if line)
