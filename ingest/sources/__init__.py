"""Source registry. Register a source by adding a factory here; nothing else changes."""

from collections.abc import Callable

from ingest.sources.base import RawRecord, Source

SOURCES: dict[str, Callable[[], Source]] = {}

__all__ = ["SOURCES", "RawRecord", "Source"]
