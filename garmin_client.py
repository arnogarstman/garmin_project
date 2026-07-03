"""Authentication against Garmin Connect, with local token caching so a
logged-in session survives an app restart without needing the password
(or an MFA code) again."""

from pathlib import Path

from garminconnect import Garmin, GarminConnectAuthenticationError

TOKEN_DIR = Path(__file__).parent / ".garmin_tokens"


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
    return api, "ok"


def complete_mfa(api: Garmin, code: str) -> None:
    """Finish a login that paused for a Garmin MFA/2FA code, then persist
    the resulting session tokens so future app runs skip login entirely."""
    api.resume_login(None, code)
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    api.client.dump(str(TOKEN_DIR))


def logout() -> None:
    import shutil

    if TOKEN_DIR.exists():
        shutil.rmtree(TOKEN_DIR)


__all__ = [
    "Garmin",
    "GarminConnectAuthenticationError",
    "TOKEN_DIR",
    "try_resume_session",
    "begin_login",
    "complete_mfa",
    "logout",
]
