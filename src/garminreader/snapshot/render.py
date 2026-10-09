"""Fills the page template, producing one self-contained HTML file: with the data
embedded (a snapshot), or with queries the page runs through a MotherDuck connector (live)."""

import json
from collections.abc import Iterable
from importlib import resources
from typing import Any

DATA_MARKER = "/*SNAPSHOT*/null"
LIVE_MARKER = "/*LIVE*/null"
APP_MARKER = "/*APP*/"

# The claude.ai connector and tool a live page queries through; declare them in the
# artifact's `mcp` capability when publishing.
LIVE_SERVER = "MotherDuck"
LIVE_TOOL = "query"


def _script_json(value: Any) -> str:
    # "</" would let a string in the data close the inline <script> element.
    return json.dumps(value, separators=(",", ":")).replace("</", "<\\/")


def _fill(snapshot: dict[str, Any] | None, live: dict[str, Any] | None) -> str:
    package = resources.files("garminreader.snapshot")
    template = package.joinpath("page.html").read_text(encoding="utf-8")
    script = "\n".join(package.joinpath(name).read_text(encoding="utf-8") for name in ("page.js", "live.js"))
    return (
        template.replace(DATA_MARKER, _script_json(snapshot))
        .replace(LIVE_MARKER, _script_json(live))
        .replace(APP_MARKER, script)
    )


def render(data: dict[str, Any]) -> str:
    """A static page with `data` (see data.load) embedded."""
    return _fill(data, None)


def render_live(database: str, queries: dict[str, str], single_row: Iterable[str], context: dict[str, Any]) -> str:
    """A page that runs `queries` (see data.live_queries) on the MotherDuck `database` when
    opened; the `single_row` ones give one row or null. `context` (see data.context) is embedded as is."""
    live = {
        "server": LIVE_SERVER,
        "tool": LIVE_TOOL,
        "database": database,
        "queries": queries,
        "single_row": sorted(single_row),
        **context,
    }
    return _fill(None, live)
