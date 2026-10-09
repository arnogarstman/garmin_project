"""Fills the page template with the payload, producing one self-contained HTML file."""

import json
from importlib import resources
from typing import Any

DATA_MARKER = "/*SNAPSHOT*/null"
APP_MARKER = "/*APP*/"


def render(data: dict[str, Any]) -> str:
    package = resources.files("garminreader.snapshot")
    template = package.joinpath("page.html").read_text(encoding="utf-8")
    script = package.joinpath("page.js").read_text(encoding="utf-8")
    # "</" would let a string in the data close the inline <script> element.
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    return template.replace(DATA_MARKER, payload).replace(APP_MARKER, script)
