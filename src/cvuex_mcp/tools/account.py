from mcp.server.mcpserver import Context, MCPServer

from cvuex_mcp.runtime import READ_ONLY, campus_session


async def quien_soy(ctx: Context) -> dict[str, str]:
    """Indica con qué cuenta del Campus Virtual de la UEx está conectado el servidor."""
    async with campus_session(ctx) as campus:
        info = await campus.site_info()
    return {"nombre": info.full_name, "usuario": info.username, "plataforma": info.site_name}


def register(mcp: MCPServer) -> None:
    mcp.add_tool(quien_soy, annotations=READ_ONLY)
