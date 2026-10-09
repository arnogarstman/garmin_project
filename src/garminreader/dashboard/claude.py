"""The one place the dashboard's newer AI features call Claude: a structured
request validated against a pydantic model. Callers cache the result."""

import anthropic
from pydantic import BaseModel

from garminreader import config

MODEL = "claude-opus-5-5"


def available() -> bool:
    return config.optional_env("ANTHROPIC_API_KEY") is not None


def parse[T: BaseModel](system: str, content: str, output_format: type[T], max_tokens: int = 16000) -> T:
    """Ask Claude for a response matching `output_format`. Raises RuntimeError
    if Claude declines or returns nothing parseable."""
    client = anthropic.Anthropic(api_key=config.require_env("ANTHROPIC_API_KEY"))
    response = client.beta.messages.parse(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": content}],
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        output_format=output_format,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined to answer.")
    if response.parsed_output is None:
        raise RuntimeError(f"Claude returned no parseable answer (stop reason: {response.stop_reason}).")
    return response.parsed_output
