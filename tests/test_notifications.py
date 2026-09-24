from helpers import FakeMoodle, load_fixture

from cvuex_mcp.campus import Campus
from cvuex_mcp.campus.notifications import recent_notifications

NOTIFICATIONS = "message_popup_get_popup_notifications"


def campus_with_notifications(answer=None) -> tuple[Campus, FakeMoodle]:
    answer = answer or load_fixture(f"{NOTIFICATIONS}__sintetico")
    fake = FakeMoodle({NOTIFICATIONS: answer})
    return Campus(fake.client()), fake


async def test_unread_notifications():
    campus, fake = campus_with_notifications()
    result = await recent_notifications(campus, unread_only=True, limit=20)

    assert result.sin_leer == 2
    forum, grade = result.notificaciones
    assert forum.model_dump() == {
        "asunto": "COMPUTACIÓN GRÁFICA: Cambio de aula para la práctica 2",
        "resumen": "Persona 2 ha publicado en Avisos: Cambio de aula para la práctica 2",
        "origen": "foro",
        "fecha": "2026-09-24T16:00+02:00",
        "leida": False,
        "url": "https://campusvirtual.unex.es/zonauex/avuex/mod/forum/discuss.php?d=64301#p120001",
    }
    assert grade.origen == "tarea"
    [call] = fake.calls
    assert (call["useridto"], call["newestfirst"], call["limit"]) == ("0", "1", "50")


async def test_all_notifications_up_to_the_limit():
    campus, fake = campus_with_notifications()
    result = await recent_notifications(campus, unread_only=False, limit=2)
    assert [n.leida for n in result.notificaciones] == [False, False]
    assert fake.calls[0]["limit"] == "2"


async def test_long_notification_summaries_are_cut():
    answer = load_fixture(f"{NOTIFICATIONS}__sintetico")
    answer["notifications"][0]["smallmessage"] = "palabra " * 100
    campus, _ = campus_with_notifications(answer)
    summary = (
        (await recent_notifications(campus, unread_only=True, limit=1)).notificaciones[0].resumen
    )
    assert len(summary) <= 301
    assert summary.endswith("…")


async def test_no_notifications():
    """Real answer: no notifications yet."""
    campus, _ = campus_with_notifications(load_fixture(f"{NOTIFICATIONS}__vacio"))
    result = await recent_notifications(campus, unread_only=True, limit=20)
    assert (result.sin_leer, result.notificaciones) == (0, [])
