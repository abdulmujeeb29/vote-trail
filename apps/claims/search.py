"""Public-source search (Tavily), bounded and cached per normalised query per day."""

from __future__ import annotations

import hashlib
from typing import Any, Protocol

import httpx
from django.conf import settings
from django.utils import timezone

from apps.core.ai import require
from apps.trust.hashing import normalize_text

from .models import WebSearchCache

MAX_RESULTS = 4
MAX_EXCERPT = 6000


class Searcher(Protocol):
    def search(self, query: str) -> list[dict[str, Any]]: ...


class TavilySearcher:
    def search(self, query: str) -> list[dict[str, Any]]:
        require("TAVILY_API_KEY")
        resp = httpx.post(
            "https://api.tavily.com/search",
            json={
                "query": query[:300],
                "max_results": MAX_RESULTS,
                "search_depth": "basic",
                "include_answer": False,
                "country": "nigeria",
                "topic": "news",
            },
            headers={"Authorization": f"Bearer {settings.TAVILY_API_KEY}"},
            timeout=30,
        )
        resp.raise_for_status()
        return [
            {
                "url": r.get("url", ""),
                "title": r.get("title", "")[:300],
                "content": (r.get("content") or "")[:MAX_EXCERPT],
                "published": r.get("published_date") or "",
            }
            for r in resp.json().get("results", [])[:MAX_RESULTS]
        ]


_override: Searcher | None = None


def set_searcher(searcher: Searcher | None) -> None:
    global _override
    _override = searcher


def cached_search(query: str) -> list[dict[str, Any]]:
    normal = normalize_text(query)
    key = hashlib.sha256(normal.encode()).hexdigest()
    today = timezone.localdate()
    hit = WebSearchCache.objects.filter(query_hash=key, day=today).first()
    if hit is not None:
        return hit.results
    results = (_override or TavilySearcher()).search(query)
    WebSearchCache.objects.update_or_create(
        query_hash=key, day=today, defaults={"query": query[:300], "results": results}
    )
    return results
