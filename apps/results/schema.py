"""EC8A extraction schema (see docs/ec8a-schema.md). Versioned; field names configurable."""

from __future__ import annotations

from typing import Any

EC8A_SCHEMA_VERSION = "ec8a-v1"
PROMPT_VERSION = "ec8a-prompt-v2"

TOTAL_FIELDS = (
    "registered",
    "accredited",
    "ballots_issued",
    "unused",
    "spoilt",
    "rejected",
    "total_valid",
    "total_used",
)
HEADER_FIELDS = ("pu_code", "pu_name", "ward", "lga", "state", "election")
FLAG_FIELDS = ("cancelled", "signed_by_agents", "stamped")


def _field(kind: str) -> dict[str, Any]:
    value: dict[str, Any] = {"type": [kind, "null"]}
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["value", "confidence", "unreadable"],
        "properties": {
            "value": value,
            "confidence": {"type": "number"},
            "unreadable": {"type": "boolean"},
        },
    }


def json_schema() -> dict[str, Any]:
    """Strict JSON schema for the model's structured output."""
    party = {
        "type": "object",
        "additionalProperties": False,
        "required": ["party", "figures", "words"],
        "properties": {
            "party": {"type": "string"},
            "figures": _field("integer"),
            "words": _field("string"),
        },
    }
    props: dict[str, Any] = {name: _field("string") for name in HEADER_FIELDS}
    props |= {name: _field("integer") for name in TOTAL_FIELDS}
    props |= {name: _field("boolean") for name in FLAG_FIELDS}
    props["parties"] = {"type": "array", "items": party}
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [*HEADER_FIELDS, *TOTAL_FIELDS, *FLAG_FIELDS, "parties"],
        "properties": props,
    }
