"""IReV source adapters. Mock (default, labelled) and a documented public stub."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from apps.elections.models import Election
from apps.geo.models import PollingUnit

from .models import IrevSheet


@dataclass(frozen=True)
class IrevRef:
    sheet: IrevSheet


class IrevSource(Protocol):
    def get_sheet(self, election: Election, pu: PollingUnit) -> IrevSheet | None: ...


class MockIrevSource:
    """Seeded IReV sheets stored locally. Always shown with a 'mock IReV' label."""

    def get_sheet(self, election: Election, pu: PollingUnit) -> IrevSheet | None:
        return IrevSheet.objects.filter(election=election, polling_unit=pu).first()


class PublicIrevSource:
    """Placeholder for the public IReV portal (https://www.inecelectionresults.ng).

    IReV publishes EC8A *images* per polling unit (election → state → LGA → ward → PU).
    There is no public API. Automated access is disabled until INEC's terms permit it or
    a data partnership exists; the same extractor would then read those images.
    """

    def get_sheet(self, election: Election, pu: PollingUnit) -> IrevSheet | None:
        raise NotImplementedError("Public IReV access is disabled. Use MockIrevSource.")


def get_source() -> IrevSource:
    return MockIrevSource()
