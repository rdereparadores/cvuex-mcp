"""Command line: session management and MCP server startup."""

import argparse
import asyncio
import sys
from pathlib import Path

from cvuex_mcp.auth import LoginError, login_with_browser
from cvuex_mcp.calendar_export import MAX_DAYS, export_calendar
from cvuex_mcp.campus import Campus, CourseNotEnrolledError
from cvuex_mcp.credentials import CredentialStore
from cvuex_mcp.formatting import human_size
from cvuex_mcp.materials.catalog import RemoteFile
from cvuex_mcp.materials.lock import SyncLockedError
from cvuex_mcp.materials.sync import SyncProgress, synchronize
from cvuex_mcp.moodle import InvalidTokenError, MoodleClient, MoodleError, new_http_client
from cvuex_mcp.rate_limit import RateLimiter
from cvuex_mcp.session import NotLoggedInError, expired_session_message, load_token, open_client
from cvuex_mcp.sites import AVUEX
from cvuex_mcp.storage import materials_dir


def login(store: CredentialStore) -> None:
    print(f"Abriendo el navegador para iniciar sesión en {AVUEX.name}...")
    credentials = asyncio.run(login_with_browser(AVUEX, notify=print))
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


def sync_materials(store: CredentialStore, course_id: int | None) -> None:
    root = materials_dir()
    print(f"Sincronizando materiales en {root}...")

    def show(event: str, remote: RemoteFile, local: Path) -> None:
        if event == "descargado":
            print(f"  ↓ {local.relative_to(root)} ({human_size(remote.size) or '0 B'})")
        elif event == "error":
            print(f"  ✗ {local.relative_to(root)}")

    async def run() -> SyncProgress:
        token = load_token(store)
        progress = SyncProgress()
        async with new_http_client() as http:
            campus = Campus(MoodleClient(AVUEX, token, http=http))
            downloader = MoodleClient(AVUEX, token, http=http, rate_limiter=RateLimiter())
            await synchronize(campus, downloader, course_id, progress, on_file=show)
        return progress

    progress = asyncio.run(run())
    print(
        f"{progress.downloaded} descargados ({human_size(progress.downloaded_bytes) or '0 B'}), "
        f"{progress.up_to_date} al día, {progress.removed} retirados del campus "
        f"(la copia local se conserva). {progress.indexed} indexados para buscar."
    )
    for document in progress.not_searchable:
        print(f"No se podrá buscar en {document}")
    for message in progress.too_big + progress.warnings:
        print(f"Aviso: {message}")


def calendar(store: CredentialStore, days: int, course_id: int | None) -> None:
    async def run():
        async with open_client(store) as moodle:
            return await export_calendar(Campus(moodle), days, course_id)

    result = asyncio.run(run())
    events = "1 evento" if result.eventos == 1 else f"{result.eventos} eventos"
    print(f"{events}, hasta el {result.hasta[:10]}, en {result.fichero}")
    print(result.como_importar)


def serve() -> None:
    # Imported here so session commands don't pay for loading the MCP SDK.
    from cvuex_mcp.server import mcp

    mcp.run("stdio")


def calendar_days(value: str) -> int:
    if not value.isdigit() or not 1 <= int(value) <= MAX_DAYS:
        raise argparse.ArgumentTypeError(f"tiene que ser un número entre 1 y {MAX_DAYS}")
    return int(value)


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
    sync_parser = commands.add_parser(
        "sincronizar", help="descargar los materiales nuevos o modificados de las asignaturas"
    )
    sync_parser.add_argument(
        "--asignatura",
        type=int,
        metavar="ID",
        help="solo esta asignatura (por defecto, las en curso)",
    )
    calendar_parser = commands.add_parser(
        "calendario", help="guardar los próximos plazos en un .ics para importarlo en un calendario"
    )
    calendar_parser.add_argument(
        "--dias",
        type=calendar_days,
        default=MAX_DAYS,
        metavar="N",
        help=f"cuántos días hacia delante, hasta {MAX_DAYS} (por defecto, todos)",
    )
    calendar_parser.add_argument(
        "--asignatura",
        type=int,
        metavar="ID",
        help="solo esta asignatura (por defecto, las en curso)",
    )
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
            case "sincronizar":
                sync_materials(store, args.asignatura)
            case "calendario":
                calendar(store, args.dias, args.asignatura)
    except InvalidTokenError:
        sys.exit(expired_session_message())
    except (
        LoginError,
        NotLoggedInError,
        MoodleError,
        SyncLockedError,
        CourseNotEnrolledError,
    ) as error:
        sys.exit(str(error))
