# syntax=docker/dockerfile:1.7
# One image for every component: the scheduled pipeline (`pipeline`) and the
# dashboard (`dashboard`, the default). Dependencies come from uv.lock only.

ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-slim-bookworm AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.20 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# Dependencies first, in their own layer: rebuilt only when the lockfile changes.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project

COPY pyproject.toml uv.lock ./
COPY src ./src
COPY transform ./transform
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev

# Ship a parsed dbt manifest, so containers do not parse the project at startup.
RUN DUCKDB_PATH=/tmp/parse.duckdb RAW_ROOT=/tmp/raw \
    /app/.venv/bin/dbt parse --quiet --project-dir transform --profiles-dir transform --target local \
    && rm -rf transform/logs


FROM python:${PYTHON_VERSION}-slim-bookworm
RUN useradd --create-home --uid 10001 app
COPY --from=build --chown=app:app /app /app
WORKDIR /app
USER app

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    DAGSTER_HOME=/tmp/dagster \
    DUCKDB_PATH=/tmp/warehouse.duckdb \
    DEMO_DUCKDB_PATH=/tmp/warehouse.duckdb \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# Health probes are defined by the platform (see infra/), against /_stcore/health.
EXPOSE 8501
CMD ["dashboard"]
