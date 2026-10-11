# CLAUDE.md

## Goal

Personal data pipeline that ingests Garmin Connect data into a local DuckDB database, with dbt models on top and a dashboard page published as a Claude artifact. Additional sources are planned: TrainMore gym visits and possibly Strava.

## About the user

Senior data engineer. Skip beginner explanations and apply proper engineering practices by default.

## Stack

- Python 3.12+
- uv for dependency management (not pip or requirements.txt)
- python-garminconnect for the Garmin source
- DuckDB for storage
- dbt-duckdb for transformations
- A static HTML page (`snapshot/`) for the dashboard, published as a Claude artifact

## Architecture

- Generic sources layer: each source implements the same interface and is pluggable, so new sources (TrainMore, Strava) can be added without touching the others.
- Each source writes raw, untransformed JSON into a raw table in DuckDB. Keep the API payload as is; add only load metadata (source, endpoint, load timestamp, etc.).
- All transformations happen in dbt, never in ingestion code.

## Layout

- `src/garminreader/ingest/`: sources (`sources/<name>/`), registry in `sources/__init__.py`, raw store in `storage.py`. The `coach` source reads the marts and stores Claude's review of each new workout as raw payloads (`endpoint = 'workout_review'`), modelled in `staging/coach/` and `marts.fct_workout_reviews`; Dagster runs dbt in two steps around it. Raw data is the `raw.payloads` table (JSON payload and params plus load metadata) with the `raw.loads` run log, written in one transaction per load.
- Garmin Coach: the Garmin source also stores the month's calendar and each adaptive Coach plan it names (`calendar`, `adaptive_training_plan`); `marts.fct_coach_workouts` holds Coach's workouts (Garmin shares the current week), shown beside each day of the page's training plan. The race goal carries a training level (`LEVELS` in `plan.js`: steady, balanced, ambitious) that sets volume growth, peak, runs per week and quality work; `potential.js` asks Claude (sample capability, on a click) for a target time and level, saved in `settings/potential` and applied to `settings/race`; the plan's recalculate button asks again when the read is missing or stale, then applies it.
- `src/garminreader/claude.py`: the only Claude API client (the workout reviews; the page's own AI features use the artifact's `sample` capability).
- `src/garminreader/db.py`: the only way to open the database (`DATABASE` in config): a local DuckDB file, or MotherDuck as `md:<name>` with `MOTHERDUCK_TOKEN`.
- `transform/`: dbt project. `staging/<source>/` tables (newest load wins), `marts/` tables (`fct_*`, `rpt_*`).
- `src/garminreader/orchestration/`: Dagster assets (raw partitioned by day, dbt via dagster-dbt) and checks.
- `.github/workflows/`: CI (`ci.yml`) and the daily refresh against MotherDuck (`refresh.yml`, see "Scheduled refresh" in the README: secrets `MOTHERDUCK_TOKEN`, `GARMIN_TOKENS` and `SECRETS_TOKEN`; it checks the connections with `uv run doctor`, resumes the saved Garmin session, never logs in with a password, and writes a refreshed session back).
- `src/garminreader/config.py`: all settings, from `.env` (see `.env.example`).
- `src/garminreader/snapshot/`: `uv run snapshot` renders the marts into one self-contained HTML page (template `page.html` + `page.js`, `review.js` for the workout reviews, `plan.js` for the training plan (column "Claude's plan"), `gym.js` for the gym days entered in it (chest, back, legs; `settings/gym`), which `meals.js` adds to the day's energy and macro targets, `adherence.js` for plan against done (it logs each day's planned session in `settings/planlog`), `events.js` for the illness, injury and travel notes marked on the charts (`settings/events`), `meals.js` for the weight goal and meal plan, `history.js` for the History tab, `goal.js` for the race goal form, `tabs.js` for the tabs (Today, Training, Nutrition, History, About), `live.js` to boot, live or embedded), for hosting as a static page such as a Claude artifact. Reads marts only.

## Commands

- `uv run ingest garmin [--since YYYY-MM-DD]`: without `--since`, resumes from the last load minus 1 day.
- `uv run ingest coach [--since YYYY-MM-DD]`: Claude reviews workouts without a review (last 7 days, or from `--since`; at most 5 per run). Needs `ANTHROPIC_API_KEY`.
- `uv run transform [dbt args]`: dbt against the configured warehouse; defaults to `build`.
- `uv run pipeline [--partition YYYY-MM-DD]`: the Dagster job in process (ingest, dbt build, checks); what the daily run executes.
- `uv run snapshot [--out PATH] [--days 365] [--live]`: static HTML snapshot of the marts; defaults to `data/snapshot.html` (gitignored with the data). `--live` (MotherDuck only) embeds no data: the page runs its queries through the viewer's MotherDuck connector when opened, one call per section (the connector caps a result at 50 KB); publish it as an artifact declaring the `mcp` capability for MotherDuck `query`, plus `db` (rules: `settings` written by `admin`) and `user` for what the page saves (the race goal at `settings/race`, the weight goal at `settings/weight`, the last meal plan at `settings/mealplan`, the plan log at `settings/planlog`, the gym days at `settings/gym`, the events at `settings/events`), and `sample` for the meal plan: the page computes each day's energy and macro targets from `marts.fct_daily_energy` and the training plan, and Claude only writes meals for them.
- `uv run workout-check`: prints `new=true` when Garmin's newest activity is not in `raw.payloads` yet; the 30-minute schedule in `refresh.yml` refreshes only then. It asks Garmin nothing outside 06:00 to 22:00 Amsterdam time or once today's workout is stored.
- `uv run garmin-tokens login|export`: create the Garmin session on your machine (with MFA) and print it as JSON for the `GARMIN_TOKENS` secret.
- `uv run dagster dev`: Dagster UI for lineage, partitions and backfills.
- `uv run doctor`: checks every connection (Garmin, database, dbt, Anthropic) with the settings from `.env`; exits non-zero on a failure.
- Checks: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`

## Engineering conventions

- Fully typed Python.
- Small, focused modules.
- Use the `logging` module, never `print`.
- Configuration via `.env`; never commit secrets or put them in code. Keep `.env` and credential/token stores gitignored.

## Writing style

- Never use em dashes in any text, comments or docs.
