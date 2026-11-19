"""Independence: decide how many truly separate sources stand behind a set of submissions.

Rules (Amara pattern): the same person, the same device, the same or a near-identical
image, near-identical text, and forwards all collapse into one origin. Repeating a
message never manufactures confirmation.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from .hashing import hamming, hex_distance, simhash
from .types import Origin, Submission

DEFAULT_PHASH_MAX = 6
DEFAULT_SIMHASH_MAX = 3


class _DSU:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def eligible(sub: Submission, min_reputation: int) -> bool:
    return sub.reputation >= min_reputation


def independent_origins(
    items: Iterable[Submission],
    *,
    phash_max: int = DEFAULT_PHASH_MAX,
    simhash_max: int = DEFAULT_SIMHASH_MAX,
    merge_similar_images: bool = True,
) -> list[Origin]:
    """Group submissions into independent origins.

    merge_similar_images=False is used for result sheets: two people photographing the same
    wall sheet produce near-identical images and must stay independent. (Re-use of a photo
    across different polling units is caught separately by the integrity check.)
    """
    subs: Sequence[Submission] = sorted(items, key=lambda s: s.id)
    n = len(subs)
    dsu = _DSU(n)
    index = {s.id: i for i, s in enumerate(subs)}
    first_by: dict[tuple[str, str], int] = {}
    text_hashes = [simhash(s.text) if s.text else None for s in subs]

    for i, s in enumerate(subs):
        for attr in ("participant_key", "device_id", "image_sha256"):
            value = getattr(s, attr)
            if value:
                key = (attr, value)
                if key in first_by:
                    dsu.union(first_by[key], i)
                else:
                    first_by[key] = i
        if s.forward_of and s.forward_of in index:
            dsu.union(index[s.forward_of], i)

    for i in range(n):
        for j in range(i + 1, n):
            a, b = subs[i], subs[j]
            d = hex_distance(a.image_phash, b.image_phash) if merge_similar_images else None
            if d is not None and d <= phash_max:
                dsu.union(i, j)
                continue
            ta, tb = text_hashes[i], text_hashes[j]
            if ta is not None and tb is not None and hamming(ta, tb) <= simhash_max:
                dsu.union(i, j)
                continue
            # Forwards of an unknown original: all forwards of similar text are one origin.
            unknown_forwards = (
                a.is_forward and b.is_forward and not a.forward_of and not b.forward_of
            )
            similar = ta is not None and tb is not None and hamming(ta, tb) <= simhash_max * 3
            if unknown_forwards and similar:
                dsu.union(i, j)

    groups: dict[int, list[Submission]] = {}
    for i, s in enumerate(subs):
        groups.setdefault(dsu.find(i), []).append(s)

    origins = []
    for members in groups.values():
        members.sort(key=lambda s: s.id)
        origins.append(
            Origin(
                key=members[0].id,
                member_ids=tuple(m.id for m in members),
                roles=frozenset(m.role for m in members),
                parties=frozenset(m.party for m in members if m.party),
                forwards_only=all(m.is_forward for m in members),
            )
        )
    origins.sort(key=lambda o: o.key)
    return origins


def is_cross_party(origins: Sequence[Origin]) -> bool:
    """True when agreeing origins include party agents from at least two different parties."""
    parties: set[str] = set()
    for o in origins:
        if "agent" in o.roles and len(o.parties) == 1:
            parties |= o.parties
    return len(parties) >= 2
