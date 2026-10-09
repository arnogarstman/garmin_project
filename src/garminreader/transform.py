"""Run dbt against the warehouse: `uv run transform [dbt args]` (default: build).

Points dbt at the project in transform/, at the raw files and at the DuckDB
file from config, so .env stays the single place for settings. Set DBT_TARGET=azure
to read raw files from Azure Data Lake Storage.
"""

import os
import sys

from dbt.cli.main import dbtRunner

from garminreader import config


def configure_dbt_env() -> None:
    """Expose the configured locations to dbt (profiles.yml and sources read them)."""
    os.environ["DUCKDB_PATH"] = str(config.duckdb_path())
    os.environ["RAW_ROOT"] = config.raw_root()
    os.environ.setdefault("DBT_PROJECT_DIR", str(config.dbt_project_dir()))
    os.environ.setdefault("DBT_PROFILES_DIR", str(config.dbt_project_dir()))


def main() -> None:
    configure_dbt_env()
    result = dbtRunner().invoke(sys.argv[1:] or ["build"])
    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
