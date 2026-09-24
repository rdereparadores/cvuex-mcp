from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from pydantic import Field

from cvuex_mcp.campus.notifications import recent_notifications
from cvuex_mcp.models import ListaNotificaciones
from cvuex_mcp.runtime import READ_ONLY, campus_session


async def notificaciones(
    ctx: Context,
    solo_no_leidas: Annotated[
        bool, Field(description="false para incluir también las ya leídas.")
    ] = True,
    limite: Annotated[int, Field(ge=1, le=50, description="Cuántas mostrar como mucho.")] = 20,
) -> ListaNotificaciones:
    """Muestra las notificaciones del campus (avisos de foros, calificaciones, entregas...),
    de la más reciente a la más antigua.

    Consultarlas no las marca como leídas. La mensajería entre usuarios está
    desactivada en el campus, así que no hay mensajes que consultar.
    """
    async with campus_session(ctx) as campus:
        return await recent_notifications(campus, unread_only=solo_no_leidas, limit=limite)


def register(mcp: MCPServer) -> None:
    mcp.add_tool(notificaciones, annotations=READ_ONLY)
