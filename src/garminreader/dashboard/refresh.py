"""Run the pipeline (ingest, then dbt) from the dashboard.

Runs as subprocesses: dbt keeps process-global state that does not belong in
a long-lived Streamlit server, and a crash there must not take the app down.
"""

import logging
import subprocess
import sys

from garminreader import config

logger = logging.getLogger(__name__)

STEPS: list[tuple[str, list[str]]] = [
    ("ingest", ["-m", "garminreader.ingest", "garmin"]),
    ("transform", ["-m", "garminreader.transform", "build"]),
]


class RefreshFailed(RuntimeError):
    pass


def run_pipeline() -> None:
    if config.is_demo():
        raise RefreshFailed("Refreshing from Garmin is disabled for demo data.")
    for name, args in STEPS:
        logger.info("Running %s", name)
        result = subprocess.run(
            [sys.executable, *args],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            output = (result.stdout + result.stderr).strip().splitlines()
            raise RefreshFailed(f"{name} failed:\n" + "\n".join(output[-15:]))
