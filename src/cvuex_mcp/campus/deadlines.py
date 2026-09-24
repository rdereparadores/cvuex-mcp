"""Deadlines and other dated events from the Moodle calendar."""

from typing import Any

from cvuex_mcp.campus.core import Campus
from cvuex_mcp.formatting import (
    calendar_day_url,
    event_kind,
    iso_datetime,
    module_type,
    short_text,
)
from cvuex_mcp.models import ListaPlazos, Plazo

DAY_SECONDS = 24 * 60 * 60
OVERDUE_LOOKBACK_DAYS = 30
MAX_EVENTS = 50  # the most Moodle returns per request
SITE_COURSE_ID = 1  # Moodle's front page, which hosts site-wide and personal events


async def upcoming_deadlines(
    campus: Campus, days: int, course_id: int | None = None
) -> ListaPlazos:
    """What's coming up in the calendar, by date, from two sources:

    - Events waiting for the student (submit, attempt...). Moodle only returns
      those still pending, so overdue ones from the last ``OVERDUE_LOOKBACK_DAYS``
      are included.
    - Every other calendar event from now on: activity openings, events the
      teacher adds, personal events... They don't require any action.
    """
    # Minute precision keeps the cache keys stable between close calls.
    now = int(campus.now()) // 60 * 60
    since = now - OVERDUE_LOOKBACK_DAYS * DAY_SECONDS
    until = now + days * DAY_SECONDS

    pending = await _action_events(campus, since, until, course_id)
    pending_ids = {event["id"] for event in pending}
    others = [
        event
        for event in await _calendar_events(campus, now, until, course_id)
        if event["id"] not in pending_ids
    ]
    course_names = {c.id: c.nombre for c in await campus.courses("all")} if others else {}

    dated = [(event["timesort"], _pending_deadline(event, now)) for event in pending]
    dated += [
        (event["timestart"], _calendar_deadline(campus, event, now, course_names))
        for event in others
    ]
    dated.sort(key=lambda pair: pair[0])
    return ListaPlazos(
        desde=iso_datetime(since),
        hasta=iso_datetime(until),
        plazos=[deadline for _, deadline in dated],
    )


async def _action_events(
    campus: Campus, since: int, until: int, course_id: int | None
) -> list[dict[str, Any]]:
    window = {"timesortfrom": since, "timesortto": until, "limitnum": MAX_EVENTS}
    if course_id is None:
        answer = await campus.call("core_calendar_get_action_events_by_timesort", **window)
    else:
        answer = await campus.call(
            "core_calendar_get_action_events_by_course", courseid=course_id, **window
        )
    return answer["events"]


async def _calendar_events(
    campus: Campus, since: int, until: int, course_id: int | None
) -> list[dict[str, Any]]:
    """All calendar events. Group events are not included: they need the group ids."""
    if course_id is None:
        course_ids = [course.id for course in await campus.courses("inprogress")]
    else:
        course_ids = [course_id]
    general_view = course_id is None  # personal and site-wide events only there
    answer = await campus.call(
        "core_calendar_get_calendar_events",
        events={"courseids": course_ids},
        options={
            "timestart": since,
            "timeend": until,
            "userevents": general_view,
            "siteevents": general_view,
        },
    )
    return answer["events"]


def _pending_deadline(event: dict[str, Any], now: int) -> Plazo:
    course = event.get("course") or {}
    action = event.get("action") or {}
    return Plazo(
        fecha=iso_datetime(event["timesort"]),
        asignatura=course.get("fullname"),
        asignatura_id=course.get("id"),
        actividad=event.get("activityname") or event["name"],
        tipo=module_type(event.get("modulename")),
        evento=event["name"],
        descripcion=short_text(event.get("description")),
        requiere_accion=True,
        accion=action.get("name") if action.get("actionable") else None,
        vencido=event["timesort"] < now,
        url=event["url"],
    )


def _calendar_deadline(
    campus: Campus, event: dict[str, Any], now: int, course_names: dict[int, str]
) -> Plazo:
    course_id = event["courseid"] if event["courseid"] in course_names else None
    return Plazo(
        fecha=iso_datetime(event["timestart"]),
        asignatura=course_names.get(event["courseid"]),
        asignatura_id=course_id,
        actividad=event["name"],
        tipo=event_kind(event["eventtype"], event.get("modulename")),
        evento=event["name"],
        descripcion=short_text(event.get("description")),
        requiere_accion=False,
        accion=None,
        vencido=event["timestart"] + event["timeduration"] < now,
        url=calendar_day_url(
            # Personal events have no course; the site (id 1) shows them.
            campus.site,
            event["courseid"] or SITE_COURSE_ID,
            event["timestart"],
            event["id"],
        ),
    )
