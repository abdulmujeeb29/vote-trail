"""INEC polling unit codes: State/LGA/Ward/PU, e.g. 37/06/01/001 (also seen as 37-06-01-001)."""

from __future__ import annotations

import re
from dataclasses import dataclass

_CODE = re.compile(r"^\s*(\d{1,2})\s*[/-]\s*(\d{1,2})\s*[/-]\s*(\d{1,2})\s*[/-]\s*(\d{1,3})\s*$")


class InvalidPUCode(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PUCode:
    state: int
    lga: int
    ward: int
    unit: int

    def __str__(self) -> str:
        return f"{self.state:02d}/{self.lga:02d}/{self.ward:02d}/{self.unit:03d}"

    @property
    def ward_code(self) -> str:
        return f"{self.state:02d}/{self.lga:02d}/{self.ward:02d}"


def parse_pu_code(raw: str) -> PUCode:
    match = _CODE.match(raw or "")
    if not match:
        raise InvalidPUCode("Polling unit codes look like 37/06/01/001.")
    state, lga, ward, unit = (int(g) for g in match.groups())
    if not (1 <= state <= 37 and lga >= 1 and ward >= 1 and unit >= 1):
        raise InvalidPUCode("Polling unit codes look like 37/06/01/001.")
    return PUCode(state, lga, ward, unit)


def normalize_pu_code(raw: str) -> str:
    return str(parse_pu_code(raw))
