"""The student's campus notifications."""

from typing import Any

from cvuex_mcp.campus.core import Campus
from cvuex_mcp.formatting import component_origin, iso_datetime, short_text
from cvuex_mcp.models import ListaNotificaciones, Notificacion

MAX_NOTIFICATIONS = 50


async def recent_notifications(
    campus: Campus, *, unread_only: bool, limit: int
) -> ListaNotificaciones:
    """The student's notifications, newest first. Reading them doesn't mark them as read.

    Moodle can't filter by read status, so for unread ones the newest
    ``MAX_NOTIFICATIONS`` are fetched and filtered here.
    """
    answer = await campus.call(
        "message_popup_get_popup_notifications",
        useridto=0,  # the current user
        newestfirst=True,
        limit=MAX_NOTIFICATIONS if unread_only else limit,
        offset=0,
    )
    notifications = [n for n in answer["notifications"] if not (unread_only and n["read"])]
    return ListaNotificaciones(
        sin_leer=answer["unreadcount"],
        notificaciones=[_notification(n) for n in notifications[:limit]],
    )


def _notification(notification: dict[str, Any]) -> Notificacion:
    summary = short_text(notification.get("smallmessage") or notification.get("text"))
    return Notificacion(
        asunto=notification["subject"],
        resumen=summary or "",
        origen=component_origin(notification.get("component")),
        fecha=iso_datetime(notification["timecreated"]),
        leida=notification["read"],
        url=notification.get("contexturl") or None,
    )
