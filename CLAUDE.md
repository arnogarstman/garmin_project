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

- `src/garminreader/ingest/`: sources (`sources/<name>/`), registry in `sources/__init__.py`, raw loader in `storage.py`. Raw tables are `raw.<source>`.
- `transform/`: dbt project. `staging/<source>/` views (newest load wins), `marts/` tables (`fct_*`, `rpt_*`).
- `src/garminreader/dashboard/`: Streamlit app. `queries.py` is its only database access and reads marts only.
- `src/garminreader/config.py`: all settings, from `.env` (see `.env.example`).

## Commands

- `uv run ingest garmin [--since YYYY-MM-DD]`: without `--since`, resumes from the last load minus 1 day.
- `uv run transform [dbt args]`: dbt against the configured warehouse; defaults to `build`.
- `uv run dashboard`
- Checks: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`

## Engineering conventions

- Fully typed Python.
- Small, focused modules.
- Use the `logging` module, never `print`.
- Configuration via `.env`; never commit secrets or put them in code. Keep `.env` and credential/token stores gitignored.

## Writing style

- Never use em dashes in any text, comments or docs.
