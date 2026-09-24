"""Development helper to build test fixtures from real Moodle answers.

    # 1. Save a real answer (secrets are removed before writing it)
    uv run scripts/moodle_fixtures.py explorar core_course_get_contents courseid=1234
    uv run scripts/moodle_fixtures.py explorar mod_assign_get_assignments 'courseids[0]=1234'

    # 2. Anonymise it into a test fixture, then REVIEW IT BY HAND before committing
    uv run scripts/moodle_fixtures.py anonimizar fixtures/raw/avuex/<fichero>.json

Raw answers contain personal data and live in fixtures/raw/, which is git-ignored.
"""

import argparse
import asyncio
import json
import re
import sys
from itertools import count
from pathlib import Path
from typing import Any

from cvuex_mcp.moodle import MoodleError
from cvuex_mcp.session import open_client
from cvuex_mcp.sites import AVUEX

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "fixtures" / "raw" / AVUEX.key
TEST_FIXTURES_DIR = ROOT / "tests" / "fixtures"

# Only reads are allowed. These "get" functions are excluded because they
# create new keys or tokens.
CREATES_CREDENTIALS = {
    "tool_mobile_get_autologin_key",
    "tool_mobile_get_tokens_for_qr_login",
    "core_calendar_get_calendar_export_token",
}

SECRET_KEYS = {"userprivateaccesskey", "token", "privatetoken", "wstoken", "sesskey"}
PERSON_NAME_KEYS = {
    "firstname",
    "lastname",
    "username",
    "userfullname",
    "userfromfullname",
    "usermodifiedfullname",
}
EMAIL_KEYS = {"email"}
# "fullname" also names courses: it is personal only inside an object describing a person.
PERSON_MARKERS = PERSON_NAME_KEYS | EMAIL_KEYS | {"profileimageurl", "userpictureurl"}
USER_ID_KEYS = {"userid", "useridfrom", "useridto", "authorid", "usermodified"}
# Official identification numbers (e.g. the student's ID); "idnumber" alone is a course code.
PERSON_ID_NUMBER_KEYS = {"useridnumber"}
FREE_TEXT_KEYS = {"text", "smallmessage", "fullmessage", "fullmessagehtml", "fullmessagetext"}
# Emails also appear inside free texts, e.g. teachers' contact in a section summary.
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")


# --- explorar ------------------------------------------------------------------


def is_read_only(function: str) -> bool:
    return "_get_" in function and function not in CREATES_CREDENTIALS


def parse_params(pairs: list[str]) -> dict[str, str]:
    """``["courseids[0]=5", "limit=3"]`` → ``{"courseids[0]": "5", "limit": "3"}``."""
    params = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep:
            sys.exit(f"Parámetro inválido '{pair}': usa nombre=valor.")
        params[key] = value
    return params


def raw_path(function: str, params: dict[str, str]) -> Path:
    suffix = "__".join(re.sub(r"[^\w]+", "-", f"{k}-{v}").strip("-") for k, v in params.items())
    return RAW_DIR / (f"{function}__{suffix}" if suffix else function)


def redact_secrets(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: "<secreto>" if k in SECRET_KEYS else redact_secrets(v) for k, v in data.items()}
    if isinstance(data, list):
        return [redact_secrets(item) for item in data]
    return data


def describe(data: Any) -> str:
    if isinstance(data, list):
        return f"lista de {len(data)} elementos"
    if isinstance(data, dict):
        parts = [f"{k} ({len(v)})" if isinstance(v, list) else k for k, v in data.items()]
        return "objeto con: " + ", ".join(parts)
    return repr(data)


def explore(function: str, params: dict[str, str]) -> None:
    if not is_read_only(function):
        sys.exit(f"'{function}' no es una función de solo lectura; no se llama.")

    async def fetch():
        async with open_client() as moodle:
            return await moodle.call(function, **params)

    try:
        result = redact_secrets(asyncio.run(fetch()))
    except MoodleError as error:
        sys.exit(f"{function}: Moodle devolvió un error ({error.errorcode}): {error}")
    path = raw_path(function, params).with_suffix(".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{path.relative_to(ROOT)}: {describe(result)}")


# --- anonimizar ----------------------------------------------------------------


class Anonymizer:
    """Replace personal data with consistent fake values.

    It works by key name, so it cannot catch everything (e.g. names inside
    a course summary): every fixture must still be reviewed by hand.
    """

    def __init__(self, max_items: int, max_text: int) -> None:
        self.max_items = max_items
        self.max_text = max_text
        self._people: dict[str, str] = {}
        self._user_ids: dict[int, int] = {}
        self._next_person = count(1)
        self._next_user_id = count(1001)

    def run(self, data: Any) -> Any:
        self._collect_people(data)
        return self._rewrite(data)

    def _collect_people(self, data: Any) -> None:
        """First pass: learn every name, username and email, so they can also be
        replaced where they appear inside other texts."""
        if isinstance(data, dict):
            is_person = not PERSON_MARKERS.isdisjoint(data)
            for key, value in data.items():
                if not (isinstance(value, str) and value):
                    self._collect_people(value)
                elif key in EMAIL_KEYS:
                    self._people.setdefault(value, f"persona{next(self._next_person)}@example.com")
                elif key in PERSON_NAME_KEYS or (key == "fullname" and is_person):
                    self._person(value)
        elif isinstance(data, list):
            for item in data:
                self._collect_people(item)

    def _person(self, real: str) -> str:
        return self._people.setdefault(real, f"Persona {next(self._next_person)}")

    def _rewrite(self, data: Any, key: str = "") -> Any:
        if isinstance(data, dict):
            return {k: self._rewrite(v, k) for k, v in data.items()}
        if isinstance(data, list):
            return [self._rewrite(item, key) for item in data[: self.max_items]]
        if key in USER_ID_KEYS and isinstance(data, int) and data > 0:
            return self._user_ids.setdefault(data, next(self._next_user_id))
        if key.endswith(("imageurl", "pictureurl")):
            return "https://moodle.example/pix/u/f1.png"
        if key.endswith("initials") and isinstance(data, str):
            return "XX"
        if key in PERSON_ID_NUMBER_KEYS and data:
            return "00000000"
        if isinstance(data, str):
            return self._rewrite_text(data, key)
        return data

    def _rewrite_text(self, text: str, key: str) -> str:
        if key in FREE_TEXT_KEYS and text:
            return "Texto de ejemplo."
        # Longest first, so "Ana María" is replaced before "Ana".
        for real in sorted(self._people, key=len, reverse=True):
            text = text.replace(real, self._people[real])
        text = EMAIL_PATTERN.sub("persona@example.com", text)
        return text if len(text) <= self.max_text else text[: self.max_text] + "…"


def anonymize(source: Path, name: str | None, max_items: int, max_text: int) -> None:
    """Write the fixture as ``tests/fixtures/<name>.json``; by default, the function name."""
    data = json.loads(source.read_text(encoding="utf-8"))
    result = Anonymizer(max_items, max_text).run(data)
    target = TEST_FIXTURES_DIR / f"{name or source.stem.split('__')[0]}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{target.relative_to(ROOT)}  ← revísalo a mano antes de hacer commit")


# --- CLI -----------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)

    explore_parser = commands.add_parser(
        "explorar", help="guardar la respuesta real de una función"
    )
    explore_parser.add_argument("function", help="función de Moodle (solo lectura)")
    explore_parser.add_argument("params", nargs="*", help="parámetros nombre=valor")

    anon_parser = commands.add_parser("anonimizar", help="crear un fixture de test anonimizado")
    anon_parser.add_argument("source", type=Path, help="fichero de fixtures/raw/")
    anon_parser.add_argument("--max-items", type=int, default=3, help="elementos por lista")
    anon_parser.add_argument("--max-text", type=int, default=300, help="caracteres por texto")
    anon_parser.add_argument("--nombre", help="nombre del fixture (por defecto, la función)")

    args = parser.parse_args()
    if args.command == "explorar":
        explore(args.function, parse_params(args.params))
    else:
        anonymize(args.source, args.nombre, args.max_items, args.max_text)


if __name__ == "__main__":
    main()
