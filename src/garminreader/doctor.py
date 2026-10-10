"""Check every external connection: `uv run doctor`.

Each check talks to the real service with the settings from .env and reports
ok, skipped (not configured and optional, or not applicable to the profile)
or failed. Exits non-zero when any check failed.
"""

import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from garminreader import config

logger = logging.getLogger("doctor")


class Status(StrEnum):
    OK = "ok"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True)
class Result:
    name: str
    status: Status
    detail: str


class Skip(Exception):
    """Raised by a check that does not apply in the current configuration."""


def check_garmin() -> str:
    if config.is_demo():
        raise Skip("demo profile uses synthetic data")
    from garminreader.ingest.sources.garmin import auth

    api = auth.connect()
    return f"logged in as {api.get_full_name()}"


def check_database() -> str:
    from garminreader import db

    database = config.database()
    if config.is_motherduck(database):
        config.require_env("MOTHERDUCK_TOKEN")
    elif not db.exists(database):
        raise Skip(f"no database at {database} yet; created by the first ingest or synthesize")
    with db.connect(read_only=True, database=database) as con:
        con.execute("select 1").fetchone()
        row = con.execute(
            "select count(*) from information_schema.tables where table_schema = 'raw' and table_name = 'payloads'"
        ).fetchone()
    has_raw = row is not None and row[0] > 0
    return f"{database} ({'raw.payloads present' if has_raw else 'no raw.payloads yet'})"


def check_dbt() -> str:
    from dbt.cli.main import dbtRunner

    from garminreader.transform import configure_dbt_env

    configure_dbt_env()
    result = dbtRunner().invoke(["debug", "--quiet"])
    if not result.success:
        raise RuntimeError("dbt debug failed; run `uv run transform debug` for details")
    return "profile and connection valid"


def check_anthropic() -> str:
    api_key = config.optional_env("ANTHROPIC_API_KEY")
    if api_key is None:
        raise Skip("ANTHROPIC_API_KEY not set; the dashboard AI features stay off")
    import anthropic

    from garminreader.dashboard.claude import MODEL

    model = anthropic.Anthropic(api_key=api_key).models.retrieve(MODEL)
    return f"key valid, {model.id} available"


CHECKS: dict[str, Callable[[], str]] = {
    "garmin": check_garmin,
    "database": check_database,
    "dbt": check_dbt,
    "anthropic": check_anthropic,
}


def run(checks: dict[str, Callable[[], str]]) -> list[Result]:
    results = []
    for name, check in checks.items():
        try:
            results.append(Result(name, Status.OK, check()))
        except Skip as skip:
            results.append(Result(name, Status.SKIPPED, str(skip)))
        except Exception as exc:
            results.append(Result(name, Status.FAILED, f"{type(exc).__name__}: {exc}"))
    return results


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger.info("Profile: %s", config.data_profile())
    results = run(CHECKS)
    for result in results:
        log = logger.error if result.status is Status.FAILED else logger.info
        log("%-10s %-8s %s", result.name, result.status, result.detail)
    sys.exit(1 if any(r.status is Status.FAILED for r in results) else 0)


if __name__ == "__main__":
    main()
