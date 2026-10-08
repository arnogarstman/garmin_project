"""Contract every source implements. Sources only fetch; they never transform."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class RawRecord:
    """One API response, kept exactly as returned.

    `endpoint` is a stable logical name (not a URL) so dbt sources survive
    upstream URL changes. `params` records what was requested, for lineage.
    """

    endpoint: str
    payload: Any
    params: dict[str, Any] = field(default_factory=dict)


class Source(Protocol):
    name: str

    def extract(self, since: date | None = None) -> Iterator[RawRecord]:
        """Yield raw records. `since` is a hint for incremental sources; a
        source may ignore it and return full history."""
        ...
