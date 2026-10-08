"""Chart color palette. One place to keep hues consistent across the app."""

import streamlit as st


def _is_dark() -> bool:
    return bool(st.get_option("theme.base") == "dark")


# Fixed categorical order: never reassigned/cycled per chart.
CATEGORICAL_LIGHT = ["#2a78d6", "#1baf7a", "#eda100", "#008300", "#4a3aa7", "#e34948"]
CATEGORICAL_DARK = ["#3987e5", "#199e70", "#c98500", "#008300", "#9085e9", "#e66767"]

# Single hue, light -> dark, for magnitude/trend lines.
SEQUENTIAL_LIGHT = "#2a78d6"
SEQUENTIAL_DARK = "#3987e5"

# Reserved status colors: never reused as a categorical series color.
STATUS = {
    "good": "#0ca30c",
    "warning": "#fab219",
    "serious": "#ec835a",
    "critical": "#d03b3b",
}

CHROME_LIGHT = {
    "surface": "#fcfcfb",
    "primary_ink": "#0b0b0b",
    "secondary_ink": "#52514e",
    "muted": "#898781",
    "grid": "#e1e0d9",
}
CHROME_DARK = {
    "surface": "#1a1a19",
    "primary_ink": "#ffffff",
    "secondary_ink": "#c3c2b7",
    "muted": "#898781",
    "grid": "#2c2c2a",
}


def categorical() -> list[str]:
    return CATEGORICAL_DARK if _is_dark() else CATEGORICAL_LIGHT


def sequential() -> str:
    return SEQUENTIAL_DARK if _is_dark() else SEQUENTIAL_LIGHT


def status(level: str) -> str:
    return STATUS[level]


def chrome() -> dict[str, str]:
    return CHROME_DARK if _is_dark() else CHROME_LIGHT
