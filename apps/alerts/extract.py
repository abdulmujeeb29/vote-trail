"""AI reads an announcement into structured, quote-checked facts."""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

from apps.core import ai

SYSTEM = """You read official Nigerian election announcements (INEC press releases, notices).
Extract ONLY facts stated in the text. For each affected polling unit give its code as printed
(e.g. 37/06/02/002) and, for relocations, the new polling unit code if printed.
quote must be copied verbatim from the text. If no polling units are named, return an empty list.
kind: pu_relocation | pvc_collection | schedule_change | other."""


def schema() -> dict[str, Any]:
    affected = {
        "type": "object",
        "additionalProperties": False,
        "required": ["pu_code", "new_pu_code", "quote"],
        "properties": {
            "pu_code": {"type": "string"},
            "new_pu_code": {"type": ["string", "null"]},
            "quote": {"type": "string"},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["kind", "affected"],
        "properties": {
            "kind": {
                "type": "string",
                "enum": ["pu_relocation", "pvc_collection", "schedule_change", "other"],
            },
            "affected": {"type": "array", "items": affected},
        },
    }


class AnnouncementReader(Protocol):
    def read(self, text: str) -> dict[str, Any]: ...


class AzureAnnouncementReader:
    def read(self, text: str) -> dict[str, Any]:
        out = ai.structured(
            system=SYSTEM,
            content=[{"type": "input_text", "text": text[:8000]}],
            schema=schema(),
            name="announcement",
        )
        return json.loads(out)


_override: AnnouncementReader | None = None


def set_reader(reader: AnnouncementReader | None) -> None:
    global _override
    _override = reader


def get_reader() -> AnnouncementReader:
    return _override or AzureAnnouncementReader()


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()
