"""Connections to the configured database: a local DuckDB file or MotherDuck."""

from pathlib import Path

import duckdb

from garminreader import config


class DatabaseNotFound(RuntimeError):
    """The configured local database file does not exist yet."""


def connect(read_only: bool = False, database: str | None = None) -> duckdb.DuckDBPyConnection:
    """Open the database. A local file is created on a write connection; MotherDuck
    databases are created on first use. MotherDuck connections are never opened
    read-only: its access control is the token, and its read-only mode is a separate share."""
    database = database or config.database()
    if config.is_motherduck(database):
        name = database.removeprefix("md:")
        con = duckdb.connect("md:")
        con.execute(f'CREATE DATABASE IF NOT EXISTS "{name}"')
        con.execute(f'USE "{name}"')
        return con
    if read_only and not exists(database):
        raise DatabaseNotFound(f"No database at {database}")
    Path(database).parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(database, read_only=read_only)


def exists(database: str | None = None) -> bool:
    """Whether the database can be opened for reading. Assumed for MotherDuck."""
    database = database or config.database()
    return config.is_motherduck(database) or Path(database).exists()
