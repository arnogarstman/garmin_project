"""Source registry. Register a source by adding a factory here; nothing else changes."""

from collections.abc import Callable

from garminreader.ingest.sources.base import RawRecord, Source
from garminreader.ingest.sources.coach.source import CoachSource
from garminreader.ingest.sources.garmin.source import GarminSource

SOURCES: dict[str, Callable[[], Source]] = {
    "garmin": GarminSource,
    "coach": CoachSource,
}

__all__ = ["SOURCES", "RawRecord", "Source"]
