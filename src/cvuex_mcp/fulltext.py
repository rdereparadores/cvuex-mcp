"""What the full-text indexes (materials, forums) share: how text is tokenized,
and how the student's words become an FTS5 query."""

import re

# Accents and case don't matter: "aplicacion" finds "Aplicación".
TOKENIZER = "unicode61 remove_diacritics 2"
# Too common to help find anything.
STOPWORDS = {
    *("a", "al", "con", "como", "de", "del", "el", "en", "es", "la", "las", "lo", "los"),
    *("o", "para", "por", "que", "se", "su", "sus", "un", "una", "uno", "y"),
}
MIN_PREFIX_LENGTH = 4
"""Longer words also match as a prefix: "protocolo" finds "protocolos"."""


def search_words(query: str) -> list[str]:
    """The student's words as FTS5 terms, quoted so no word acts as an operator."""
    words = [w for w in re.findall(r"\w+", query.casefold()) if w not in STOPWORDS]
    return [f'"{w}"*' if len(w) >= MIN_PREFIX_LENGTH else f'"{w}"' for w in words]


def all_or_any(words: list[str]) -> list[tuple[str, bool]]:
    """The FTS5 queries to try in order, and whether each one needs every word."""
    if len(words) <= 1:
        return [(" ".join(words), True)]
    return [(" ".join(words), True), (" OR ".join(words), False)]
