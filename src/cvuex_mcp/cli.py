"""Command line: session management and MCP server startup."""

import argparse
import asyncio
import sys

from cvuex_mcp.auth import LoginError, login_with_browser
from cvuex_mcp.campus import Campus
from cvuex_mcp.credentials import CredentialStore
from cvuex_mcp.moodle import InvalidTokenError, MoodleError
from cvuex_mcp.session import NotLoggedInError, expired_session_message, open_client
from cvuex_mcp.sites import AVUEX


def login(store: CredentialStore) -> None:
    print(f"Abriendo el navegador para iniciar sesión en {AVUEX.name}...")
    credentials = asyncio.run(login_with_browser(AVUEX))
    store.save(AVUEX.key, credentials)
    print(f"Sesión guardada en {store.path}")


def whoami(store: CredentialStore, *, list_functions: bool) -> None:
    async def fetch():
        async with open_client(store) as moodle:
            return await Campus(moodle).site_info()

    info = asyncio.run(fetch())
    print(f"{info.full_name} ({info.username}) en {info.site_name}")
    print(f"Moodle {info.moodle_release} · {len(info.functions)} funciones disponibles")
    if list_functions:
        print("\n".join(info.functions))


def logout(store: CredentialStore) -> None:
    if store.delete(AVUEX.key):
        print("Credenciales borradas de este equipo.")
        print("El token sigue siendo válido en Moodle hasta que caduque.")
    else:
        print("No había ninguna sesión guardada.")


def serve() -> None:
    # Imported here so session commands don't pay for loading the MCP SDK.
    from cvuex_mcp.server import mcp

    mcp.run("stdio")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cvuex-mcp", description="Servidor MCP del Campus Virtual de la UEx (AVUEx)."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("login", help="iniciar sesión con la cuenta UEx")
    whoami_parser = commands.add_parser("whoami", help="comprobar la sesión guardada")
    whoami_parser.add_argument(
        "--functions", action="store_true", help="listar las funciones de la API disponibles"
    )
    commands.add_parser("logout", help="borrar la sesión guardada")
    commands.add_parser("serve", help="arrancar el servidor MCP (stdio)")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "serve":
        serve()
        return

    store = CredentialStore()
    try:
        match args.command:
            case "login":
                login(store)
            case "whoami":
                whoami(store, list_functions=args.functions)
            case "logout":
                logout(store)
    except InvalidTokenError:
        sys.exit(expired_session_message())
    except (LoginError, NotLoggedInError, MoodleError) as error:
        sys.exit(str(error))
