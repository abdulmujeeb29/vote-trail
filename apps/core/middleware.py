"""Request ID and anonymous visitor identity (signed, HttpOnly cookie)."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.core import signing

from .logging import request_id_var


class RequestIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        token = request_id_var.set(rid)
        try:
            response = self.get_response(request)
        finally:
            request_id_var.reset(token)
        response["X-Request-ID"] = rid
        return response


class VisitorIdentityMiddleware:
    """Assign every browser a random visitor UUID. No account needed."""

    salt = "votetrail.visitor"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        name = settings.VISITOR_COOKIE_NAME
        visitor_id = None
        raw = request.COOKIES.get(name)
        if raw:
            try:
                visitor_id = signing.loads(raw, salt=self.salt)
            except signing.BadSignature:
                visitor_id = None
        is_new = visitor_id is None
        if is_new:
            visitor_id = uuid.uuid4().hex
        request.visitor_id = visitor_id
        response = self.get_response(request)
        if is_new:
            response.set_cookie(
                name,
                signing.dumps(visitor_id, salt=self.salt),
                max_age=settings.VISITOR_COOKIE_MAX_AGE,
                httponly=True,
                samesite="Lax",
                secure=not settings.DEBUG and request.is_secure(),
            )
        return response


class SecurityHeadersMiddleware:
    """Content Security Policy and Permissions Policy. No inline scripts are allowed."""

    def __init__(self, get_response):
        self.get_response = get_response
        from urllib.parse import urlparse

        realtime = urlparse(settings.AZURE_REALTIME_ENDPOINT).netloc
        connect = ["'self'"] + ([f"https://{realtime}"] if realtime else [])
        self.csp = "; ".join(
            [
                "default-src 'self'",
                "script-src 'self'",
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
                "font-src 'self' https://fonts.gstatic.com",
                "img-src 'self' data: blob:",
                "media-src 'self' blob:",
                f"connect-src {' '.join(connect)}",
                "worker-src 'self'",
                "manifest-src 'self'",
                "frame-ancestors 'none'",
                "base-uri 'self'",
                "form-action 'self'",
            ]
        )

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Content-Security-Policy", self.csp)
        response.setdefault(
            "Permissions-Policy", "camera=(self), microphone=(self), geolocation=(self), payment=()"
        )
        response.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        return response


class HealthCheckMiddleware:
    """Let platform health probes through the HTTPS redirect and the host check.

    Platforms probe the container directly over plain HTTP, by IP or `localhost`. For
    /healthz only, treat the probe as HTTPS and as addressed to our own host. It still passes
    through every other middleware (security headers, cookies).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/healthz":
            hosts = [h for h in settings.ALLOWED_HOSTS if h != "*" and not h.startswith(".")]
            if hosts:
                request.META["HTTP_HOST"] = hosts[0]
            request.META["wsgi.url_scheme"] = "https"
            proxy = getattr(settings, "SECURE_PROXY_SSL_HEADER", None)
            if proxy:
                request.META[proxy[0]] = proxy[1]
        return self.get_response(request)
