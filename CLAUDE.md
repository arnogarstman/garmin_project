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
- dbt-duckdb for transformations (later)

## Architecture

- Generic sources layer: each source implements the same interface and is pluggable, so new sources (TrainMore, Strava) can be added without touching the others.
- Each source writes raw, untransformed JSON into a raw table in DuckDB. Keep the API payload as is; add only load metadata (source, endpoint, load timestamp, etc.).
- All transformations happen in dbt, never in ingestion code.

## Engineering conventions

- Fully typed Python.
- Small, focused modules.
- Use the `logging` module, never `print`.
- Configuration via `.env`; never commit secrets or put them in code. Keep `.env` and credential/token stores gitignored.

## Writing style

- Never use em dashes in any text, comments or docs.
