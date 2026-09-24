"""Tests for the fixture tooling, which keeps personal data out of the repository."""

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from moodle_fixtures import (  # noqa: E402
    SECRET_KEYS,
    TEST_FIXTURES_DIR,
    Anonymizer,
    is_read_only,
    redact_secrets,
)


def anonymize(data):
    return Anonymizer(max_items=10, max_text=1000).run(data)


def test_only_read_functions_are_explored():
    assert is_read_only("core_course_get_contents")
    assert not is_read_only("mod_assign_save_submission")
    assert not is_read_only("mod_forum_view_forum")
    assert not is_read_only("tool_mobile_get_autologin_key")


def test_secrets_are_redacted_at_any_depth():
    data = {"userprivateaccesskey": "k", "items": [{"token": "t", "name": "x"}]}
    assert redact_secrets(data) == {
        "userprivateaccesskey": "<secreto>",
        "items": [{"token": "<secreto>", "name": "x"}],
    }


def test_person_data_is_replaced_consistently():
    data = {
        "author": {"fullname": "Ana Pérez", "email": "ana@unex.es", "userid": 42},
        "post": {"subject": "Duda de Ana Pérez", "userid": 42},
    }
    result = anonymize(data)
    fake_name = result["author"]["fullname"]
    assert fake_name.startswith("Persona")
    assert result["author"]["email"].endswith("@example.com")
    assert result["post"]["subject"] == f"Duda de {fake_name}"
    assert result["author"]["userid"] == result["post"]["userid"] != 42


def test_course_names_are_kept():
    course = {"fullname": "COMPUTACIÓN GRÁFICA", "shortname": "32337"}
    assert anonymize({"courses": [course]}) == {"courses": [course]}


def test_free_texts_are_replaced_and_lists_trimmed():
    data = {"messages": [{"text": "privado"}] * 5}
    result = Anonymizer(max_items=2, max_text=1000).run(data)
    assert result == {"messages": [{"text": "Texto de ejemplo."}] * 2}


@pytest.mark.parametrize("fixture", sorted(TEST_FIXTURES_DIR.glob("*.json")), ids=lambda p: p.name)
def test_committed_fixtures_contain_no_secrets(fixture):
    def secret_values(data):
        if isinstance(data, dict):
            for key, value in data.items():
                if key in SECRET_KEYS:
                    yield value
                yield from secret_values(value)
        elif isinstance(data, list):
            for item in data:
                yield from secret_values(item)

    data = json.loads(fixture.read_text(encoding="utf-8"))
    assert all(value == "<secreto>" for value in secret_values(data))


def test_emails_inside_texts_are_replaced():
    data = {"summary": "<p>Profesora: Ana, ana.perez@unex.es</p>"}
    assert anonymize(data) == {"summary": "<p>Profesora: Ana, persona@example.com</p>"}
