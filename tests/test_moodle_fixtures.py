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


def test_forum_author_fields_are_replaced():
    post = {"userfullname": "Ana Pérez", "userinitials": "AP", "usermodified": 42}
    result = anonymize({"post": post})["post"]
    assert result["userfullname"].startswith("Persona")
    assert result["userinitials"] == "XX"
    assert result["usermodified"] != 42


def test_personal_id_numbers_are_replaced_but_course_codes_kept():
    data = {"useridnumber": "12345678", "courseidnumber": "24735", "idnumber": "24735"}
    assert anonymize(data) == {
        "useridnumber": "00000000",
        "courseidnumber": "24735",
        "idnumber": "24735",
    }


def test_post_authors_are_replaced_with_their_profile_links():
    author = {
        "id": 42,
        "fullname": "Ana Pérez",
        "initials": "AP",
        "urls": {
            "profile": "https://campus/user/view.php?id=42&course=7",
            "profileimage": "https://campus/pluginfile.php/99/user/icon/f1",
        },
    }
    post = {"id": 5, "label": "Aviso por Ana Pérez", "author": author}
    result = anonymize({"posts": [post]})["posts"][0]
    fake_id = result["author"]["id"]
    assert fake_id != 42
    assert result["id"] == 5
    assert result["label"] == f"Aviso por {result['author']['fullname']}"
    assert result["author"]["urls"] == {
        "profile": f"https://campus/user/view.php?id={fake_id}&course=7",
        "profileimage": "https://moodle.example/pix/u/f1.png",
    }


def test_course_contacts_are_people():
    """A course's teachers come as just an id and a name, the same as in their profiles."""
    contacts = [{"id": 42, "fullname": "Ana"}]
    course = {"id": 7, "fullname": "COMPUTACIÓN GRÁFICA", "contacts": contacts}
    profile = {
        "id": 42,
        "fullname": "Ana",
        "email": "ana@unex.es",
        "description": "<p>Tutorías: lunes. Tel. 924 000 000</p>",
        "city": "Badajoz",
        "profileimageurlsmall": "https://campus/pluginfile.php/99/user/icon/f2",
    }
    result = anonymize({"courses": [course], "users": [profile]})
    [contact] = result["courses"][0]["contacts"]
    [user] = result["users"]
    assert result["courses"][0]["fullname"] == "COMPUTACIÓN GRÁFICA"
    assert contact["id"] == user["id"] != 42
    assert contact["fullname"] == user["fullname"] != "Ana"
    assert user["description"] == user["city"] == "Texto de ejemplo."
    assert user["profileimageurlsmall"] == "https://moodle.example/pix/u/f1.png"
