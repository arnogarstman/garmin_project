"""Run dbt against the warehouse: `uv run transform [dbt args]` (default: build).

Points dbt at the project in transform/ and at the DuckDB file from config,
so .env stays the single place for settings.
"""

import os
import sys

from dbt.cli.main import dbtRunner

from garminreader import config


def main() -> None:
    os.environ["DUCKDB_PATH"] = str(config.duckdb_path())
    os.environ.setdefault("DBT_PROJECT_DIR", str(config.dbt_project_dir()))
    os.environ.setdefault("DBT_PROFILES_DIR", str(config.dbt_project_dir()))
    result = dbtRunner().invoke(sys.argv[1:] or ["build"])
    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
