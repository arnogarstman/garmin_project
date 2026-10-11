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

- `src/garminreader/ingest/`: sources (`sources/<name>/`), registry in `sources/__init__.py`, raw store in `storage.py`. The `coach` source reads the marts and stores Claude's review of each new workout as raw payloads (`endpoint = 'workout_review'`), modelled in `staging/coach/` and `marts.fct_workout_reviews`; Dagster runs dbt in two steps around it. Raw data is the `raw.payloads` table (JSON payload and params plus load metadata) with the `raw.loads` run log, written in one transaction per load.
- `src/garminreader/claude.py`: the only Claude API client (workout reviews and the dashboard's AI features).
- `src/garminreader/db.py`: the only way to open the database (`DATABASE` in config): a local DuckDB file, or MotherDuck as `md:<name>` with `MOTHERDUCK_TOKEN`.
- `transform/`: dbt project. `staging/<source>/` tables (newest load wins), `marts/` tables (`fct_*`, `rpt_*`).
- `src/garminreader/orchestration/`: Dagster assets (raw partitioned by day, dbt via dagster-dbt) and checks.
- `.github/workflows/`: CI (`ci.yml`) and the daily refresh against MotherDuck (`refresh.yml`, see "Scheduled refresh" in the README: secrets `MOTHERDUCK_TOKEN`, `GARMIN_TOKENS` and `SECRETS_TOKEN`; it checks the connections with `uv run doctor`, resumes the saved Garmin session, never logs in with a password, and writes a refreshed session back).
- `src/garminreader/dashboard/`: Streamlit app. `queries.py` is its only database access and reads marts only.
- `src/garminreader/config.py`: all settings, from `.env` (see `.env.example`).
- `src/garminreader/snapshot/`: `uv run snapshot` renders the marts into one self-contained HTML page (template `page.html` + `page.js`, `review.js` for the workout reviews, `plan.js` for the training plan, `meals.js` for the weight goal and meal plan, `goal.js` for the race goal form, `tabs.js` for the tabs (Today, Training, Nutrition, History, About), `live.js` to boot, live or embedded), for hosting as a static page such as a Claude artifact. Reads marts only.
- `src/garminreader/synthetic/`: demo data. A simulated athlete rendered as raw Garmin API responses, so the real pipeline runs on it unchanged.
- `DATA_PROFILE`: `prod` (default, your data in `data/`) or `demo` (synthetic, in `data/demo/`, safe to publish). Real ingest is refused in demo; `synthesize` is refused in prod.

## Commands

- `uv run ingest garmin [--since YYYY-MM-DD]`: without `--since`, resumes from the last load minus 1 day.
- `uv run ingest coach [--since YYYY-MM-DD]`: Claude reviews workouts without a review (last 7 days, or from `--since`; at most 5 per run). Needs `ANTHROPIC_API_KEY`.
- `uv run transform [dbt args]`: dbt against the configured warehouse; defaults to `build`.
- `uv run dashboard`
- `DATA_PROFILE=demo uv run synthesize [--days 365] [--seed 42]`: rebuilds the demo warehouse from scratch, ending today; follow with `DATA_PROFILE=demo uv run transform`.
- `uv run pipeline [--partition YYYY-MM-DD]`: the Dagster job in process (ingest, dbt build, checks); what the daily run executes.
- `uv run snapshot [--out PATH] [--days 365] [--live]`: static HTML snapshot of the marts; defaults to `data/[demo/]snapshot.html` (gitignored with the data). `--live` (MotherDuck only) embeds no data: the page runs its queries through the viewer's MotherDuck connector when opened, one call per section (the connector caps a result at 50 KB); publish it as an artifact declaring the `mcp` capability for MotherDuck `query`, plus `db` (rules: `settings` written by `admin`) and `user` for what the page saves (the race goal at `settings/race`, the weight goal at `settings/weight`, the last meal plan at `settings/mealplan`), and `sample` for the meal plan: the page computes each day's energy and macro targets from `marts.fct_daily_energy` and the training plan, and Claude only writes meals for them.
- `uv run workout-check`: prints `new=true` when Garmin's newest activity is not in `raw.payloads` yet; the 30-minute schedule in `refresh.yml` refreshes only then. It asks Garmin nothing outside 06:00 to 22:00 Amsterdam time or once today's workout is stored.
- `uv run garmin-tokens login|export`: create the Garmin session on your machine (with MFA) and print it as JSON for the `GARMIN_TOKENS` secret.
- `uv run dagster dev`: Dagster UI for lineage, partitions and backfills.
- `uv run doctor`: checks every connection (Garmin, database, dbt, Anthropic) with the settings from `.env`; exits non-zero on a failure.
- `uv run explore`: DuckDB UI on a snapshot of a local warehouse taken at startup; never blocks ingest or transform. For MotherDuck use its web UI.
- Checks: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`

## Engineering conventions

- Fully typed Python.
- Small, focused modules.
- Use the `logging` module, never `print`.
- Configuration via `.env`; never commit secrets or put them in code. Keep `.env` and credential/token stores gitignored.

## Writing style

- Never use em dashes in any text, comments or docs.
