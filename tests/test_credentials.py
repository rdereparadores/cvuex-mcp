import os
import stat

import pytest

from cvuex_mcp.credentials import (
    HOME_ENV_VAR,
    Credentials,
    CredentialStore,
    default_credentials_path,
)


@pytest.fixture
def store(tmp_path) -> CredentialStore:
    return CredentialStore(tmp_path / "config" / "credentials.json")


def test_round_trip_per_key(store):
    store.save("avuex", Credentials("a", "pa"))
    store.save("otra", Credentials("e"))
    assert store.load("avuex") == Credentials("a", "pa")
    assert store.load("otra") == Credentials("e", None)


def test_missing_file_means_no_credentials(store):
    assert store.load("avuex") is None
    assert store.delete("avuex") is False


def test_delete_keeps_other_entries(store):
    store.save("avuex", Credentials("a"))
    store.save("otra", Credentials("e"))
    assert store.delete("avuex") is True
    assert store.load("avuex") is None
    assert store.load("otra") == Credentials("e")


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions")
def test_file_is_private(store):
    store.save("avuex", Credentials("a"))
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600


def test_home_can_be_overridden(tmp_path, monkeypatch):
    monkeypatch.setenv(HOME_ENV_VAR, str(tmp_path))
    assert default_credentials_path() == tmp_path / "credentials.json"
