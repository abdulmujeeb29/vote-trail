"""EC8A extraction: AI reads, the server validates, low confidence goes to human review."""

from __future__ import annotations

import base64
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol

from django.conf import settings

from apps.core import ai
from apps.geo.codes import InvalidPUCode, normalize_pu_code
from apps.trust.types import SheetFigures

from .models import Extraction
from .schema import EC8A_SCHEMA_VERSION, PROMPT_VERSION, TOTAL_FIELDS, json_schema
from .words import words_to_int

SYSTEM_PROMPT = """You read photos of Nigerian INEC Form EC8A (polling unit result sheet).
Return ONLY what is written on the sheet, in the JSON schema provided.
Rules:
- Never guess. If a value is smudged, cut off, covered or ambiguous, set value to null,
  unreadable to true, and confidence below 0.5.
- confidence is your honest probability (0-1) that the value is exactly right.
- Party scores: copy the figures as an integer and the words exactly as written.
- Use the party acronym exactly as printed on the sheet.
- cancelled is true only if the sheet is endorsed "Result Cancelled", "NULL AND VOID" or similar.
- Do not compute or correct totals. Copy what is written, even if it does not add up.
- pu_code is the code printed on the sheet, e.g. 37/06/02/004.
- Handwritten digits that could be read two ways (4/9, 1/7, 3/8, 5/6, 0/6) must get
  confidence below 0.8 unless the written words or other entries confirm the reading.
- Ink blots, smudges, tears or glare over a number: unreadable=true, value=null.
  Never reconstruct a covered number from totals.
"""


class Extractor(Protocol):
    model: str

    def read(self, image: bytes, context: dict[str, Any]) -> dict[str, Any]: ...


class AzureExtractor:
    @property
    def model(self) -> str:
        return settings.AZURE_OPENAI_DEPLOYMENT

    def read(self, image: bytes, context: dict[str, Any]) -> dict[str, Any]:
        b64 = base64.b64encode(image).decode()
        hint = (
            f"Expected polling unit: {context.get('pu_code', 'unknown')}. "
            f"Parties on the ballot: {', '.join(context.get('parties', []))}."
        )
        text = ai.structured(
            system=SYSTEM_PROMPT,
            content=[
                {"type": "input_text", "text": hint},
                {"type": "input_image", "image_url": f"data:image/jpeg;base64,{b64}"},
            ],
            schema=json_schema(),
            name="ec8a",
        )
        return json.loads(text)


_override: Extractor | None = None


def set_extractor(extractor: Extractor | None) -> None:
    """Swap the extractor (tests, demo builds). None restores the Azure extractor."""
    global _override
    _override = extractor


class DemoExtractor:
    """Deterministic reader for browser tests: returns a clean sheet for the expected PU.

    Only enabled with EXTRACTOR_BACKEND=demo. Never used for real results.
    """

    model = "demo-extractor"

    def read(self, image: bytes, context: dict[str, Any]) -> dict[str, Any]:
        from .synth import SheetSpec, truth

        parties = context.get("parties") or ["PA", "PB"]
        votes = {p: 100 + 10 * i for i, p in enumerate(parties)}
        spec = SheetSpec(
            pu_code=context.get("pu_code", ""), pu_name="", ward="", lga="", parties=votes
        )
        return truth(spec)


def get_extractor() -> Extractor:
    if _override is not None:
        return _override
    if settings.EXTRACTOR_BACKEND == "demo":
        return DemoExtractor()
    return AzureExtractor()


@dataclass
class Normalised:
    figures: dict[str, Any]
    low_confidence: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _value(raw: dict[str, Any], name: str) -> Any:
    item = raw.get(name) or {}
    return item.get("value")


def _shaky(item: dict[str, Any] | None, min_conf: float) -> bool:
    if not item:
        return True
    return bool(item.get("unreadable")) or float(item.get("confidence") or 0) < min_conf


def normalise(
    raw: dict[str, Any],
    *,
    expected_pu: str,
    parties: Iterable[str],
    min_confidence: float | None = None,
) -> Normalised:
    """Validate model output and convert it into figures for the trust rules."""
    min_conf = settings.EXTRACTION_MIN_CONFIDENCE if min_confidence is None else min_confidence
    allowed = {p.upper() for p in parties}
    out = Normalised(figures={})
    party_votes: dict[str, int] = {}
    words: dict[str, int | None] = {}
    for row in raw.get("parties") or []:
        acr = str(row.get("party") or "").strip().upper()
        if not acr:
            continue
        if allowed and acr not in allowed:
            out.errors.append(f"unknown_party:{acr}")
            out.low_confidence.append(f"party:{acr}")
            continue
        fig = row.get("figures") or {}
        value = fig.get("value")
        if not isinstance(value, int) or isinstance(value, bool):
            out.low_confidence.append(f"party:{acr}")
            continue
        if _shaky(fig, min_conf):
            out.low_confidence.append(f"party:{acr}")
        party_votes[acr] = value
        word_item = row.get("words") or {}
        if word_item.get("value") and not word_item.get("unreadable"):
            words[acr] = words_to_int(word_item.get("value"))
    missing = sorted(allowed - set(party_votes) - {f.split(":")[1] for f in out.low_confidence})
    for acr in missing:
        out.low_confidence.append(f"party:{acr}")
        out.errors.append(f"missing_party:{acr}")

    for name in TOTAL_FIELDS:
        item = raw.get(name) or {}
        value = item.get("value")
        if value is None:
            if item.get("unreadable"):
                out.low_confidence.append(name)
            out.figures[name] = None
            continue
        if not isinstance(value, int) or isinstance(value, bool):
            out.errors.append(f"not_integer:{name}")
            out.low_confidence.append(name)
            out.figures[name] = None
            continue
        if _shaky(item, min_conf):
            out.low_confidence.append(name)
        out.figures[name] = value

    printed = _value(raw, "pu_code")
    if printed:
        try:
            if normalize_pu_code(str(printed)) != normalize_pu_code(expected_pu):
                out.errors.append("pu_code_mismatch")
                out.low_confidence.append("pu_code")
        except InvalidPUCode:
            out.errors.append("pu_code_unreadable")
    cancelled_item = raw.get("cancelled") or {}
    out.figures["cancelled"] = bool(cancelled_item.get("value"))
    out.figures["party_votes"] = party_votes
    out.figures["words"] = words
    out.figures["signed_by_agents"] = _value(raw, "signed_by_agents")
    out.low_confidence = sorted(set(out.low_confidence))
    return out


def figures_from_json(
    data: dict[str, Any] | None, low_confidence: Iterable[str] = ()
) -> SheetFigures:
    data = data or {}
    return SheetFigures(
        party_votes=dict(data.get("party_votes") or {}),
        words=dict(data.get("words") or {}),
        cancelled=bool(data.get("cancelled")),
        low_confidence_fields=tuple(low_confidence),
        **{name: data.get(name) for name in TOTAL_FIELDS},
    )


def extract(image: bytes, sha256: str, *, pu_code: str, parties: list[str]) -> Extraction:
    """Read an image once per (image, schema, prompt, model); reuse otherwise."""
    extractor = get_extractor()
    key = {
        "image_sha256": sha256,
        "schema_version": EC8A_SCHEMA_VERSION,
        "prompt_version": PROMPT_VERSION,
        "model": extractor.model,
    }
    existing = Extraction.objects.filter(**key).first()
    if existing is not None:
        return existing
    raw = extractor.read(image, {"pu_code": pu_code, "parties": parties})
    norm = normalise(raw, expected_pu=pu_code, parties=parties)
    return Extraction.objects.create(
        **key,
        raw=raw,
        figures=norm.figures,
        low_confidence_fields=norm.low_confidence,
        errors=norm.errors,
    )
