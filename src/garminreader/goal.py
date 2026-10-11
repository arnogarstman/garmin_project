"""The athlete's training goal as a JSON file at `config.goal_path()` (a local file, or object
storage in the cloud). It is user input, not warehouse data: the workout reviews read it, and the
dashboard page embeds it when no race is saved on the page itself."""

import logging
from datetime import date
from pathlib import Path

import fsspec
from pydantic import BaseModel, ValidationError

from garminreader import config

logger = logging.getLogger(__name__)

DEFAULT_HORIZON_WEEKS = 12


class TrainingGoal(BaseModel):
    goal: str
    target: str = ""
    event_date: date | None = None
    weekly_hours: float | None = None
    experience: str = "Intermediate"
    constraints: str = ""

    def weeks_to_event(self, today: date) -> int | None:
        if self.event_date is None or self.event_date < today:
            return None
        return (self.event_date - today).days // 7

    def describe(self, today: date) -> str:
        """The goal as prompt text."""
        lines = [f"- Goal: {self.goal}"]
        if self.target:
            lines.append(f"- Target: {self.target}")
        weeks = self.weeks_to_event(today)
        if self.event_date is not None:
            lines.append(f"- Event date: {self.event_date.isoformat()} ({weeks} weeks from today)")
        else:
            lines.append(f"- No fixed event date; plan the next {DEFAULT_HORIZON_WEEKS} weeks")
        if self.weekly_hours is not None:
            lines.append(f"- Time available for training: {self.weekly_hours:g} hours per week")
        lines.append(f"- Self-described experience: {self.experience}")
        if self.constraints:
            lines.append(f"- Constraints, injuries or preferences: {self.constraints}")
        return "\n".join(lines)


def load_goal(location: str | Path | None = None) -> TrainingGoal | None:
    """The saved goal at a local path or fsspec URL (default: config.goal_path())."""
    fs, path = fsspec.core.url_to_fs(str(location or config.goal_path()))
    if not fs.exists(path):
        return None
    try:
        with fs.open(path, "r") as f:
            return TrainingGoal.model_validate_json(f.read())
    except ValidationError:
        logger.warning("Ignoring unreadable goal file %s", path)
        return None
