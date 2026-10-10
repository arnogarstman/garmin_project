"""Manage the saved Garmin session for scheduled runs: `uv run garmin-tokens login|export`.

Scheduled runs never log in with a password (see config.garmin_password_login): they resume
the session saved here, passed in as the GARMIN_TOKENS secret. `login` creates that session on
your own machine, asking for an MFA code if Garmin wants one; `export` writes it as JSON to
stdout, for `uv run garmin-tokens export | gh secret set GARMIN_TOKENS`.
"""

import argparse
import logging
import sys

from garminreader import config
from garminreader.ingest.sources.garmin import auth

logger = logging.getLogger("garmin-tokens")


def login() -> None:
    """A fresh password login (with MFA when asked), saved to the token directory."""
    api, status = auth.begin_login(config.require_env("GARMIN_EMAIL"), config.require_env("GARMIN_PASSWORD"))
    if status == "mfa":
        auth.complete_mfa(api, input("Garmin MFA code: ").strip())
    logger.info("Garmin session saved in %s", auth.TOKEN_DIR)


def export() -> str:
    """The saved session as JSON, after checking that it still works."""
    api = auth.try_resume_session()
    if api is None:
        raise SystemExit(f"No working Garmin session in {auth.TOKEN_DIR}; run `uv run garmin-tokens login` first")
    tokens: str = api.client.dumps()
    return tokens


def main() -> None:
    parser = argparse.ArgumentParser(prog="garmin-tokens", description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["login", "export"])
    args = parser.parse_args()
    # Logs go to stderr, so `export` writes nothing but the token JSON to stdout.
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.command == "login":
        login()
    else:
        sys.stdout.write(export() + "\n")


if __name__ == "__main__":
    main()
