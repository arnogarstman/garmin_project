"""Authentication against Garmin Connect, with local token caching so a
logged-in session survives an app restart without needing the password
(or an MFA code) again."""

import sys

from garminconnect import Garmin, GarminConnectAuthenticationError

from garminreader import config

TOKEN_DIR = config.garmin_token_dir()


def try_resume_session() -> Garmin | None:
    """Attempt to restore a session purely from cached tokens on disk.
    Returns a ready-to-use client, or None if there is no valid cached session."""
    if not TOKEN_DIR.exists():
        return None
    api = Garmin(return_on_mfa=True)
    try:
        mfa_status, _ = api.login(tokenstore=str(TOKEN_DIR))
    except Exception:
        return None
    if mfa_status == "needs_mfa":
        return None
    return api


def begin_login(email: str, password: str) -> tuple[Garmin, str]:
    """Start a login with credentials. Returns (client, status) where status
    is "ok" (fully logged in) or "mfa" (needs a verification code)."""
    api = Garmin(email=email, password=password, return_on_mfa=True)
    mfa_status, _ = api.login(tokenstore=str(TOKEN_DIR))
    if mfa_status == "needs_mfa":
        return api, "mfa"
    # With return_on_mfa=True, garminconnect returns early on a non-MFA login
    # without persisting tokens or loading the profile. Persist, then resume
    # from the fresh tokens to get a fully initialised client.
    _persist_tokens(api)
    resumed = try_resume_session()
    if resumed is None:
        raise GarminConnectAuthenticationError("Login succeeded but session could not be resumed from saved tokens")
    return resumed, "ok"


def complete_mfa(api: Garmin, code: str) -> None:
    """Finish a login that paused for a Garmin MFA/2FA code, then persist
    the resulting session tokens so future app runs skip login entirely."""
    api.resume_login(None, code)
    _persist_tokens(api)


def connect() -> Garmin:
    """Session for unattended use: cached tokens first, then GARMIN_EMAIL and
    GARMIN_PASSWORD from .env. Asks for an MFA code only on a terminal."""
    api = try_resume_session()
    if api is not None:
        return api
    api, status = begin_login(config.require_env("GARMIN_EMAIL"), config.require_env("GARMIN_PASSWORD"))
    if status == "mfa":
        if not sys.stdin.isatty():
            raise GarminConnectAuthenticationError("Garmin wants an MFA code; run the ingest once in a terminal")
        complete_mfa(api, input("Garmin MFA code: ").strip())
    return api


def _persist_tokens(api: Garmin) -> None:
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    api.client.dump(str(TOKEN_DIR))


__all__ = [
    "TOKEN_DIR",
    "Garmin",
    "GarminConnectAuthenticationError",
    "begin_login",
    "complete_mfa",
    "connect",
    "try_resume_session",
]
