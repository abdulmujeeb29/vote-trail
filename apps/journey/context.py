def profile(request):
    """Expose the voter profile to every template (single source of truth)."""
    if not hasattr(request, "visitor_id"):
        return {}
    from .profile import BETA, get_profile

    try:
        p = get_profile(request)
    except Exception:  # DB not ready (e.g. migrations)
        return {}
    return {"me": p, "BETA": BETA}
