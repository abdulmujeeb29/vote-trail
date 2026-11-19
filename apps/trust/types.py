from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum


class ResultStatus(StrEnum):
    PENDING = "pending"
    MATCHES = "matches"
    MISMATCH = "mismatch"
    NEEDS_REVIEW = "needs_review"
    CANCELLED = "cancelled"


class ClaimStatus(StrEnum):
    UNCONFIRMED = "unconfirmed"
    CORROBORATED = "corroborated"
    CONFIRMED_BY_SOURCE = "confirmed_by_source"
    REFUTED_BY_SOURCE = "refuted_by_source"


class Stance(StrEnum):
    SUPPORTS = "supports"
    OPPOSES = "opposes"
    IRRELEVANT = "irrelevant"


class Severity(StrEnum):
    REJECT = "reject"  # the item is excluded entirely
    REVIEW = "review"  # forces human review
    INFO = "info"  # shown, no effect on status


@dataclass(frozen=True, slots=True)
class Reason:
    code: str
    detail: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Submission:
    """Anything a person sent us: a photo upload, a report, a forwarded message."""

    id: str
    participant_key: str = ""  # phone HMAC or visitor id
    device_id: str = ""
    role: str = "voter"
    party: str = ""
    reputation: int = 0
    image_sha256: str = ""
    image_phash: str = ""  # hex perceptual hash
    text: str = ""
    is_forward: bool = False
    forward_of: str = ""  # id of the submission this forwards, if known
    source_domain: str = ""
    observed_at: dt.datetime | None = None


@dataclass(frozen=True, slots=True)
class Origin:
    """A group of submissions that count as ONE independent source."""

    key: str
    member_ids: tuple[str, ...]
    roles: frozenset[str]
    parties: frozenset[str]
    forwards_only: bool


@dataclass(frozen=True, slots=True)
class SheetFigures:
    """Figures from one EC8A sheet (citizen photo or IReV image)."""

    party_votes: Mapping[str, int]
    registered: int | None = None
    accredited: int | None = None
    rejected: int | None = None
    total_valid: int | None = None
    total_used: int | None = None
    ballots_issued: int | None = None
    unused: int | None = None
    spoilt: int | None = None
    words: Mapping[str, int | None] = field(default_factory=dict)
    cancelled: bool = False
    low_confidence_fields: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Violation:
    code: str
    detail: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Flag:
    code: str
    severity: Severity
    detail: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CitizenSheet:
    submission: Submission
    figures: SheetFigures
    flags: tuple[Flag, ...] = ()


@dataclass(frozen=True, slots=True)
class Evidence:
    id: str
    submission: Submission
    stance: Stance
    explicit: bool = False  # explicitly confirms/refutes (needed for authority verdicts)


@dataclass(frozen=True, slots=True)
class Decision:
    status: str
    reasons: tuple[Reason, ...] = ()
    origin_count: int = 0
    forward_count: int = 0
    cross_party: bool = False
    authority: str = ""
    location: str = ""
    diffs: Mapping[str, tuple[int | None, int | None]] = field(default_factory=dict)

    @property
    def reason_codes(self) -> frozenset[str]:
        return frozenset(r.code for r in self.reasons)
