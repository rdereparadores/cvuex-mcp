"""The MCP tools, one module per area.

Each tool function is named like the tool the assistant sees, and each module
registers its tools with ``register``.
"""

from mcp.server.mcpserver import MCPServer

from cvuex_mcp.tools import (
    account,
    assignments,
    changes,
    courses,
    deadlines,
    forums,
    grades,
    notifications,
    quizzes,
)

AREAS = (account, courses, deadlines, assignments, changes, notifications, forums, grades, quizzes)


def register_all(mcp: MCPServer) -> None:
    for area in AREAS:
        area.register(mcp)
