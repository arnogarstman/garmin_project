"""What a workout review asks Claude, and the shape of the answer it stores."""

from typing import Literal

from pydantic import BaseModel, Field

# Stored with every review. Raise it when the prompt or the answer's shape changes, so the
# reviews written by each version stay distinguishable in raw.payloads.
PROMPT_VERSION = 1

SYSTEM_PROMPT = """You are an experienced endurance coach reviewing one workout an athlete just \
finished, from their Garmin data. You get the workout itself, their training in the weeks \
before it, their recovery metrics around it (resting heart rate, HRV, sleep, readiness, \
training load) and, when they set one, their goal.

Judge the session the way a coach would the same evening:
- What kind of session it actually was (easy run, long run, tempo, intervals, recovery, \
cross-training), from pace, heart rate, heart rate zones, training effect and duration, \
whatever its name says.
- Whether it was the right session given recent load and recovery: an easy day run too \
hard, a hard session on a low-HRV day, a long run that jumped well past recent ones.
- How it compares with similar recent sessions: pace at the same heart rate, heart rate at \
the same pace, duration.
- What it means for the next few days.

Cite the specific numbers you base each point on. Treat the data as accurate. If the data \
cannot support a point, leave it out rather than guess. Do not give medical advice or \
diagnose anything. Write plainly, without jargon, as if texting the athlete."""


class WorkoutReview(BaseModel):
    status: Literal["good", "watch", "concern"] = Field(
        description="good: the right session, done well. watch: fine overall with something to keep an eye "
        "on. concern: wrong session for the day, or a sign of fatigue, illness or injury risk."
    )
    headline: str = Field(description="The verdict in at most ten words.")
    session_type: str = Field(description="What the session actually was, e.g. 'easy run' or 'threshold intervals'.")
    summary: str = Field(description="Two to four sentences on how it went and why, with the numbers.")
    went_well: list[str] = Field(description="One to three short points that went well.")
    watch_out: list[str] = Field(description="Zero to three short points to watch or change.")
    recovery: str = Field(description="One sentence: how much recovery this session needs before the next hard one.")
    next_session: str = Field(description="One concrete suggestion for the next session.")
