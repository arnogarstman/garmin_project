import json
from typing import Any

import pytest

from garminreader.ingest.sources.garmin import auth, tokens


class FakeClient:
    def dumps(self) -> str:
        return json.dumps({"di_token": "access", "di_refresh_token": "refresh", "di_client_id": "client"})


class FakeGarmin:
    client = FakeClient()


def test_scheduled_run_never_falls_back_to_a_password_login(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a working session and with password login disabled, connect fails before any login."""
    monkeypatch.setattr(auth, "try_resume_session", lambda: None)
    monkeypatch.setenv("GARMIN_PASSWORD_LOGIN", "false")
    monkeypatch.setenv("GARMIN_EMAIL", "athlete@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "secret")

    def no_login(*_: Any) -> Any:
        raise AssertionError("password login attempted")

    monkeypatch.setattr(auth, "begin_login", no_login)
    with pytest.raises(auth.GarminConnectAuthenticationError, match="garmin-tokens login"):
        auth.connect()


def test_a_saved_session_is_used_without_a_login(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeGarmin()
    monkeypatch.setattr(auth, "try_resume_session", lambda: session)
    monkeypatch.setenv("GARMIN_PASSWORD_LOGIN", "false")
    assert auth.connect() is session


@pytest.mark.parametrize(
    ("value", "allowed"), [(None, True), ("true", True), ("false", False), ("0", False), ("No", False)]
)
def test_password_login_setting(monkeypatch: pytest.MonkeyPatch, value: str | None, allowed: bool) -> None:
    from garminreader import config

    if value is None:
        monkeypatch.delenv("GARMIN_PASSWORD_LOGIN", raising=False)
    else:
        monkeypatch.setenv("GARMIN_PASSWORD_LOGIN", value)
    assert config.garmin_password_login() is allowed


def test_export_writes_the_session_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "try_resume_session", lambda: FakeGarmin())
    assert json.loads(tokens.export())["di_refresh_token"] == "refresh"


def test_export_refuses_without_a_working_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "try_resume_session", lambda: None)
    with pytest.raises(SystemExit, match="garmin-tokens login"):
        tokens.export()


def test_a_fresh_login_ignores_the_saved_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """A refused saved session must not stop a password login: login() gets no tokenstore."""
    calls: list[dict[str, Any]] = []

    class Api:
        def __init__(self, **_: Any) -> None:
            pass

        def login(self, **kwargs: Any) -> tuple[str, None]:
            calls.append(kwargs)
            return "needs_mfa", None

    monkeypatch.setattr(auth, "Garmin", Api)
    monkeypatch.setenv("GARMINTOKENS", "{}")
    _, status = auth.begin_login("athlete@example.com", "secret")
    assert status == "mfa"
    assert calls == [{}]
