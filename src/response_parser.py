import json
import re

from pydantic import BaseModel, field_validator


class ParsedAnalysis(BaseModel):
    modification_tag: str
    summary: str
    risk_notes: list[str]
    test_checklist: list[str]

    @field_validator("modification_tag")
    @classmethod
    def tag_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("modification_tag must not be empty")
        return v.strip()

    @field_validator("summary")
    @classmethod
    def summary_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("summary must not be empty")
        return v.strip()


def parse_response(raw: str) -> ParsedAnalysis:
    """
    Parse and validate JSON from Nova Pro response.

    Strips accidental markdown fences, validates required keys,
    and returns a typed ParsedAnalysis Pydantic model.
    Raises ValueError on malformed response.
    """
    # Strip markdown fences if present
    cleaned = raw.strip()
    fence_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", cleaned)
    if fence_match:
        cleaned = fence_match.group(1)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Response is not valid JSON: {exc}") from exc

    required_keys = {"modification_tag", "summary", "risk_notes", "test_checklist"}
    missing = required_keys - data.keys()
    if missing:
        raise ValueError(f"Response missing required keys: {missing}")

    for list_key in ("risk_notes", "test_checklist"):
        if not isinstance(data[list_key], list):
            raise ValueError(f"'{list_key}' must be a list, got {type(data[list_key]).__name__}")

    return ParsedAnalysis(**data)
