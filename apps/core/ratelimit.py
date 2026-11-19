"""Small fixed-window rate limiter on Django's cache."""

from __future__ import annotations

import time

from django.core.cache import cache


def hit(key: str, limit: int, window_s: int) -> bool:
    """Record a hit. Returns False when the limit is exceeded."""
    bucket = f"rl:{key}:{int(time.time() // window_s)}"
    added = cache.add(bucket, 1, timeout=window_s + 5)
    count = 1 if added else cache.incr(bucket)
    return count <= limit


def client_ip(request) -> str:
    """Client IP. X-Forwarded-For is trusted only through TRUSTED_PROXY_COUNT proxies.

    With N trusted proxies in front of the app, the real client is the N-th address from the
    right. Anything further left was written by the client and can be spoofed.
    """
    from django.conf import settings

    remote = request.META.get("REMOTE_ADDR", "")
    hops = settings.TRUSTED_PROXY_COUNT
    if hops <= 0:
        return remote
    chain = [
        p.strip() for p in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if p.strip()
    ]
    return chain[-hops] if len(chain) >= hops else remote
