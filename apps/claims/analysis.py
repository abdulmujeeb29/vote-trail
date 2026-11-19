"""AI claim analysis with server-side quote/reference validation (Amara pattern)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

from django.utils.dateparse import parse_datetime

from apps.core import ai

ANALYSIS_VERSION = "claims-v1"

SYSTEM = """You assess evidence about an election-day claim in Nigeria.
For EACH evidence item decide whether it supports the claim, opposes it, or is irrelevant.
Rules:
- Use only the text of each item. Do not use outside knowledge.
- quote: copy an EXACT sentence or phrase from the item that justifies the stance (verbatim).
  If nothing in the item is relevant, stance=irrelevant and quote="".
- observed_at: ISO time when the event was OBSERVED, only if the item states it. Never use the
  publication time. Otherwise null.
- explicit: true only if the item is an official statement that directly confirms or denies
  the claim.
- Do not judge who is right. Do not add safety advice. Do not name political winners.
"""


def schema() -> dict[str, Any]:
    item = {
        "type": "object",
        "additionalProperties": False,
        "required": ["id", "stance", "quote", "observed_at", "explicit"],
        "properties": {
            "id": {"type": "string"},
            "stance": {"type": "string", "enum": ["supports", "opposes", "irrelevant"]},
            "quote": {"type": "string"},
            "observed_at": {"type": ["string", "null"]},
            "explicit": {"type": "boolean"},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["items"],
        "properties": {"items": {"type": "array", "items": item}},
    }


class ClaimAnalyzer(Protocol):
    model: str

    def analyse(self, claim: str, items: list[dict[str, str]]) -> dict[str, Any]: ...


class AzureClaimAnalyzer:
    @property
    def model(self) -> str:
        from django.conf import settings

        return settings.AZURE_OPENAI_DEPLOYMENT

    def analyse(self, claim: str, items: list[dict[str, str]]) -> dict[str, Any]:
        payload = json.dumps({"claim": claim, "items": items}, ensure_ascii=False)
        text = ai.structured(
            system=SYSTEM,
            content=[{"type": "input_text", "text": payload}],
            schema=schema(),
            name="claim_analysis",
        )
        return json.loads(text)


_override: ClaimAnalyzer | None = None


def set_analyzer(analyzer: ClaimAnalyzer | None) -> None:
    global _override
    _override = analyzer


def get_analyzer() -> ClaimAnalyzer:
    return _override or AzureClaimAnalyzer()


@dataclass(frozen=True)
class ValidatedItem:
    id: str
    stance: str
    quote: str
    observed_at: Any
    explicit: bool


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def validate(raw: dict[str, Any], items: dict[str, str]) -> tuple[list[ValidatedItem], list[str]]:
    """Keep only items whose id exists and whose quote appears verbatim in that item."""
    valid, dropped = [], []
    seen = set()
    for row in raw.get("items") or []:
        item_id = str(row.get("id", ""))
        if item_id not in items or item_id in seen:
            dropped.append(f"unknown_or_duplicate_id:{item_id}")
            continue
        seen.add(item_id)
        stance = row.get("stance")
        quote = (row.get("quote") or "").strip()
        if stance not in ("supports", "opposes", "irrelevant"):
            dropped.append(f"bad_stance:{item_id}")
            continue
        if stance != "irrelevant" and (not quote or _squash(quote) not in _squash(items[item_id])):
            dropped.append(f"quote_not_found:{item_id}")
            continue
        observed = parse_datetime(row["observed_at"]) if row.get("observed_at") else None
        if observed is not None and observed.tzinfo is None:
            observed = None
        valid.append(ValidatedItem(item_id, stance, quote, observed, bool(row.get("explicit"))))
    return valid, dropped
