"""Verifier access: password login + SMS one-time code (2FA), roles enforced on every view."""

from __future__ import annotations

from functools import wraps

from django.shortcuts import redirect

from apps.core.models import Role

OTP_SESSION_KEY = "vt_otp_ok"
DASHBOARD_ROLES = {Role.VERIFIER, Role.OBSERVER}


def is_dashboard_user(user) -> bool:
    if not user.is_authenticated:
        return False
    p = getattr(user, "participant", None)
    return bool(p and p.is_verified and p.role in DASHBOARD_ROLES and p.phone_hmac)


def verifier_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"/dashboard/login/?next={request.path}")
        if not is_dashboard_user(request.user):
            return redirect("/dashboard/login/?denied=1")
        if not request.session.get(OTP_SESSION_KEY):
            return redirect("/dashboard/verify/")
        return view(request, *args, **kwargs)

    return wrapped
