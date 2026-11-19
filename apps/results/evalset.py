"""Build and score the EC8A evaluation set."""

from __future__ import annotations

import json
import random
from dataclasses import asdict
from pathlib import Path
from typing import Any

from django.conf import settings

from apps.trust.arithmetic import check_arithmetic

from .extract import figures_from_json, normalise
from .schema import TOTAL_FIELDS
from .synth import SheetSpec, render, truth

EVAL_DIR = Path(settings.BASE_DIR) / "fixtures" / "ec8a" / "synthetic"
PU_POOL = [
    ("37/06/01/001", "Area I, Sect. I/Area I Pri. Sch. I", "City Centre", "Municipal"),
    ("37/06/01/004", "Area Ii, Sect. Ii/F.G. Guest House", "City Centre", "Municipal"),
    ("37/06/02/004", "Garki Village Ii/New Pri. Sch.", "Garki", "Municipal"),
    ("37/02/01/003", "Bwari Sarki / Near Chief Palace", "Bwari Central", "Bwari"),
    ("37/02/02/004", "Kuchiko C.D.S. / Old Gss Bwari", "Kuduru", "Bwari"),
]
PARTY_POOL = ["PA", "PB", "PC", "PD", "PE", "PF"]


def specs(n: int = 32) -> list[SheetSpec]:
    rnd = random.Random(2027)
    out = []
    for i in range(n):
        code, name, ward, lga = PU_POOL[i % len(PU_POOL)]
        k = rnd.choice([3, 4, 4, 5, 6])
        parties = {p: rnd.randint(0, 420) for p in PARTY_POOL[:k]}
        spec = SheetSpec(
            pu_code=code,
            pu_name=name,
            ward=ward,
            lga=lga,
            parties=parties,
            registered=rnd.randint(1100, 2400),
            rejected=rnd.randint(0, 25),
            spoilt=rnd.randint(0, 4),
            seed=1000 + i,
            damage=["none", "light", "light", "heavy"][i % 4],
        )
        if i in (5, 17, 29):
            spec.override_total_valid = spec.total_valid + rnd.choice([-20, 10, 100])
        if i in (8, 22):
            spec.cancelled = True
        if i in (11, 19, 26, 31):
            spec.smudge = rnd.choice([f"party:{list(parties)[1]}", "rejected"])
        out.append(spec)
    return out


def build(n: int = 32, directory: Path = EVAL_DIR) -> int:
    directory.mkdir(parents=True, exist_ok=True)
    for i, spec in enumerate(specs(n)):
        stem = directory / f"ec8a_{i:02d}"
        stem.with_suffix(".jpg").write_bytes(render(spec))
        meta = {"spec": asdict(spec), "truth": truth(spec), "parties": list(spec.parties)}
        stem.with_suffix(".json").write_text(json.dumps(meta, indent=1, sort_keys=True))
    return n


def _truth_fields(t: dict[str, Any]) -> dict[str, tuple[Any, bool]]:
    fields = {name: (t[name]["value"], t[name]["unreadable"]) for name in TOTAL_FIELDS}
    for row in t["parties"]:
        fields[f"party:{row['party']}"] = (row["figures"]["value"], row["figures"]["unreadable"])
    fields["cancelled"] = (t["cancelled"]["value"], False)
    return fields


def score_one(raw: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    t = meta["truth"]
    norm = normalise(raw, expected_pu=t["pu_code"]["value"], parties=meta["parties"])
    got = {name: norm.figures.get(name) for name in TOTAL_FIELDS}
    got |= {f"party:{p}": v for p, v in norm.figures["party_votes"].items()}
    got["cancelled"] = norm.figures["cancelled"]
    low = set(norm.low_confidence)
    rows = []
    for name, (expected, unreadable) in _truth_fields(t).items():
        value = got.get(name)
        flagged = name in low
        if unreadable:
            ok = flagged or value is None
            kind = "smudge_flagged" if ok else "smudge_guessed"
        else:
            ok = value == expected
            kind = "correct" if ok else ("wrong_flagged" if flagged else "silent_wrong")
        rows.append(
            {
                "field": name,
                "expected": expected,
                "got": value,
                "flagged": flagged,
                "ok": ok,
                "kind": kind,
            }
        )
    sheet = figures_from_json(norm.figures, norm.low_confidence)
    routed_to_review = bool(norm.low_confidence) or bool(check_arithmetic(sheet))
    wrong = [r for r in rows if not r["ok"]]
    return {
        "rows": rows,
        "exact": not wrong,
        "routed_to_review": routed_to_review,
        # The number that matters: a wrong value that would be published without review.
        "system_silent_wrong": bool(wrong) and not routed_to_review,
    }


def summarise(results: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [r for res in results for r in res["rows"]]
    readable = [r for r in rows if r["kind"] in ("correct", "wrong_flagged", "silent_wrong")]
    confident = [r for r in readable if not r["flagged"]]
    return {
        "sheets": len(results),
        "fields": len(rows),
        "field_accuracy": round(sum(r["ok"] for r in rows) / max(len(rows), 1), 4),
        "readable_accuracy": round(sum(r["ok"] for r in readable) / max(len(readable), 1), 4),
        "sheet_exact": round(sum(res["exact"] for res in results) / max(len(results), 1), 4),
        "silent_wrong": sum(r["kind"] == "silent_wrong" for r in rows),
        "smudge_guessed": sum(r["kind"] == "smudge_guessed" for r in rows),
        "confident_accuracy": round(sum(r["ok"] for r in confident) / max(len(confident), 1), 4),
        "flag_rate": round(sum(r["flagged"] for r in rows) / max(len(rows), 1), 4),
        "sheets_routed_to_review": sum(res["routed_to_review"] for res in results),
        "system_silent_wrong_sheets": sum(res["system_silent_wrong"] for res in results),
    }
