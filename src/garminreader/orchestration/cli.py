"""Run the daily pipeline once, in process: `uv run pipeline [--partition YYYY-MM-DD]`.

This is what the scheduled cloud container executes. It runs the Dagster job
with an ephemeral instance (no daemon, no database): the run's logs go to
stdout, and the exit code tells the scheduler whether it succeeded. Without
--partition, real data runs today's partition (in Europe/Amsterdam).
"""

import argparse
import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import dagster as dg

from garminreader import config


def main() -> None:
    parser = argparse.ArgumentParser(prog="pipeline", description=__doc__.splitlines()[0])
    parser.add_argument("--partition", default=None, help="day to ingest (default today); ignored for the demo")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    from garminreader.orchestration import assets
    from garminreader.orchestration.definitions import JOB_NAME, defs

    partition = None
    if not config.is_demo():
        partition = args.partition or datetime.now(ZoneInfo(assets.TIMEZONE)).date().isoformat()
    result = defs.resolve_job_def(JOB_NAME).execute_in_process(
        partition_key=partition, instance=dg.DagsterInstance.ephemeral(), raise_on_error=False
    )
    failed_checks = [
        evaluation.check_name
        for evaluation in result.get_asset_check_evaluations()
        if not evaluation.passed and evaluation.severity == dg.AssetCheckSeverity.ERROR
    ]
    if failed_checks:
        logging.getLogger("pipeline").error("Failed checks: %s", ", ".join(failed_checks))
    sys.exit(0 if result.success and not failed_checks else 1)


if __name__ == "__main__":
    main()
