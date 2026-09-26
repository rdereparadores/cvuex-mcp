"""File and folder names that work on Windows, macOS and Linux."""

import re
import unicodedata

MAX_NAME_LENGTH = 100
# Not allowed on Windows (and "/" nowhere), plus control characters.
FORBIDDEN_CHARACTERS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def safe_name(name: str) -> str:
    """A single path component: no separators, no ``..``, not reserved, not too long."""
    name = FORBIDDEN_CHARACTERS.sub("_", unicodedata.normalize("NFC", name))
    name = " ".join(name.split()).rstrip(". ")  # Windows drops trailing dots and spaces
    if not name.strip("."):
        return "_"
    if name.split(".")[0].upper() in WINDOWS_RESERVED_NAMES:
        name = f"_{name}"
    if len(name) > MAX_NAME_LENGTH:
        stem, dot, extension = name.rpartition(".")
        keep = extension if dot and len(extension) <= 10 else ""
        cut = MAX_NAME_LENGTH - len(keep) - (1 if keep else 0)
        name = (stem if keep else name)[:cut].rstrip(". ") + (f".{keep}" if keep else "")
    return name


def section_folder(number: int, name: str) -> str:
    """``(3, "Tema 2")`` → ``"03 - Tema 2"``, so sections sort as in the course."""
    return safe_name(f"{number:02d} - {name}")


def numbered(name: str, copy: int) -> str:
    """``("notas.pdf", 2)`` → ``"notas (2).pdf"``, for names already taken."""
    stem, dot, extension = name.rpartition(".")
    if not dot or not stem:
        return f"{name} ({copy})"
    return f"{stem} ({copy}).{extension}"
