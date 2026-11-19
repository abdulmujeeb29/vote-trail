"""Tools the voice assistant can call. Every factual answer comes from here or the KB."""

from __future__ import annotations

from typing import Any

from apps.claims.models import Claim
from apps.claims.services import find_claim
from apps.claims.verdicts import render as render_verdict
from apps.elections.models import Election
from apps.geo.codes import InvalidPUCode
from apps.geo.models import PollingUnit
from apps.results import presenters
from apps.results.models import ResultCheck

from . import kb
from .refusals import refusal_for

TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "lookup_pu",
        "description": (
            "Find a polling unit by code (e.g. 37/06/02/004 or 370602004) or by place name."
        ),
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "get_result_status",
        "description": "Citizen check of a polling unit's result sheet against IReV.",
        "parameters": {
            "type": "object",
            "properties": {"pu_code": {"type": "string"}},
            "required": ["pu_code"],
        },
    },
    {
        "type": "function",
        "name": "check_claim",
        "description": "Look up what is known about a rumour or incident report.",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "type": "function",
        "name": "kb_search",
        "description": (
            "Search official, sourced facts about registration, PVC collection, "
            "transfer, election day, results, accessibility, dates and fake websites."
        ),
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
]


def _pu(query: str) -> PollingUnit | None:
    from apps.channels.ussd import parse_ussd_pu

    try:
        return PollingUnit.objects.filter(code=parse_ussd_pu(query)).first()
    except InvalidPUCode:
        words = [w for w in query.split() if len(w) > 2]
        qs = PollingUnit.objects.all()
        for w in words[:4]:
            qs = qs.filter(name__icontains=w)
        return qs.first() if words else None


def lookup_pu(query: str) -> dict[str, Any]:
    pu = _pu(query)
    if pu is None:
        return {
            "found": False,
            "say": "I couldn't find that polling unit. Check the code on your voter's card.",
        }
    cur = pu.current
    out: dict[str, Any] = {
        "found": True,
        "code": pu.code,
        "name": pu.name,
        "ward": pu.ward.name,
        "lga": pu.ward.lga.name,
    }
    if cur.pk != pu.pk:
        out["moved_to"] = {
            "code": cur.code,
            "name": cur.name,
            "landmark": cur.landmark,
            "accessibility": cur.accessibility_notes,
        }
    return out


def get_result_status(pu_code: str) -> dict[str, Any]:
    pu = _pu(pu_code)
    if pu is None:
        return {"found": False}
    election = Election.objects.order_by("-date").first()
    check = ResultCheck.objects.filter(election=election, polling_unit=pu).first()
    status = check.status if check else "pending"
    return {
        "found": True,
        "code": pu.code,
        "status": presenters.STATUS_LABEL[status],
        "explain": presenters.explain(check),
        "note": "VoteTrail compares citizen photos with IReV. Only INEC declares results.",
    }


def check_claim(text: str, language: str = "en") -> dict[str, Any]:
    claim = find_claim(text, "other")
    if claim is None:
        return {
            "known": False,
            "say": "We have no reports about that yet. You can report it and we'll check it.",
        }
    v = render_verdict(claim.latest, language)
    return {
        "known": True,
        "status": v["status"],
        "headline": v["headline"],
        "reasons": v["reasons"],
        "unknown": v["unknown"],
    }


def kb_search(query: str) -> dict[str, Any]:
    results = kb.search(query)
    if not results:
        return {
            "found": False,
            "say": "I don't know. Check INEC's official website or your local INEC office.",
        }
    return {"found": True, "results": results}


DISPATCH = {
    "lookup_pu": lookup_pu,
    "get_result_status": get_result_status,
    "check_claim": check_claim,
    "kb_search": kb_search,
}


def call(name: str, args: dict[str, Any], language: str = "en") -> dict[str, Any]:
    if name not in DISPATCH:
        return {"error": f"Unknown tool {name}"}
    text = " ".join(str(v) for v in args.values())
    refusal = refusal_for(text)
    if refusal:
        return {"refuse": True, "say": refusal}
    fn = DISPATCH[name]
    if name == "check_claim":
        return check_claim(str(args.get("text", "")), language)
    return fn(**{k: str(v) for k, v in args.items() if k in fn.__code__.co_varnames})


def claim_count() -> int:
    return Claim.objects.count()
