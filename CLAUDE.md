# CLAUDE.md

## Goal

Personal data pipeline that ingests Garmin Connect data into a local DuckDB database, with dbt models on top and a dashboard later. Additional sources are planned: TrainMore gym visits and possibly Strava.

## About the user

Senior data engineer. Skip beginner explanations and apply proper engineering practices by default.

## Stack

- Python 3.12+
- uv for dependency management (not pip or requirements.txt)
- python-garminconnect for the Garmin source
- DuckDB for storage
- dbt-duckdb for transformations
- Streamlit for the dashboard

## Architecture

- Generic sources layer: each source implements the same interface and is pluggable, so new sources (TrainMore, Strava) can be added without touching the others.
- Each source writes raw, untransformed JSON into a raw table in DuckDB. Keep the API payload as is; add only load metadata (source, endpoint, load timestamp, etc.).
- All transformations happen in dbt, never in ingestion code.

## Layout

- `src/garminreader/ingest/`: sources (`sources/<name>/`), registry in `sources/__init__.py`, raw store in `storage.py`. Raw data is the `raw.payloads` table (JSON payload and params plus load metadata) with the `raw.loads` run log, written in one transaction per load.
- `src/garminreader/db.py`: the only way to open the database (`DATABASE` in config): a local DuckDB file, or MotherDuck as `md:<name>` with `MOTHERDUCK_TOKEN`.
- `transform/`: dbt project. `staging/<source>/` tables (newest load wins), `marts/` tables (`fct_*`, `rpt_*`).
- `src/garminreader/orchestration/`: Dagster assets (raw partitioned by day, dbt via dagster-dbt) and checks.
- `.github/workflows/`: CI.
- `src/garminreader/dashboard/`: Streamlit app. `queries.py` is its only database access and reads marts only.
- `src/garminreader/config.py`: all settings, from `.env` (see `.env.example`).
- `src/garminreader/snapshot/`: `uv run snapshot` renders the marts into one self-contained HTML page (template `page.html` + `page.js`, `plan.js` for the training plan, `goal.js` for the race goal form, `live.js` to boot, live or embedded), for hosting as a static page such as a Claude artifact. Reads marts only.
- `src/garminreader/synthetic/`: demo data. A simulated athlete rendered as raw Garmin API responses, so the real pipeline runs on it unchanged.
- `DATA_PROFILE`: `prod` (default, your data in `data/`) or `demo` (synthetic, in `data/demo/`, safe to publish). Real ingest is refused in demo; `synthesize` is refused in prod.

## Commands

- `uv run ingest garmin [--since YYYY-MM-DD]`: without `--since`, resumes from the last load minus 1 day.
- `uv run transform [dbt args]`: dbt against the configured warehouse; defaults to `build`.
- `uv run dashboard`
- `DATA_PROFILE=demo uv run synthesize [--days 365] [--seed 42]`: rebuilds the demo warehouse from scratch, ending today; follow with `DATA_PROFILE=demo uv run transform`.
- `uv run pipeline [--partition YYYY-MM-DD]`: the Dagster job in process (ingest, dbt build, checks); what the daily run executes.
- `uv run snapshot [--out PATH] [--days 365] [--live]`: static HTML snapshot of the marts; defaults to `data/[demo/]snapshot.html` (gitignored with the data). `--live` (MotherDuck only) embeds no data: the page runs its queries through the viewer's MotherDuck connector when opened, one call per section (the connector caps a result at 50 KB); publish it as an artifact declaring the `mcp` capability for MotherDuck `query`, plus `db` (rules: `settings` written by `admin`) and `user` for the race goal the page saves at `settings/race`.
- `uv run dagster dev`: Dagster UI for lineage, partitions and backfills.
- `uv run explore`: DuckDB UI on a snapshot of a local warehouse taken at startup; never blocks ingest or transform. For MotherDuck use its web UI.
- Checks: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`

## Engineering conventions

- Fully typed Python.
- Small, focused modules.
- Use the `logging` module, never `print`.
- Configuration via `.env`; never commit secrets or put them in code. Keep `.env` and credential/token stores gitignored.

## Writing style

- Never use em dashes in any text, comments or docs.
