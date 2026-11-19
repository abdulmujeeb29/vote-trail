"""Import every module that registers job handlers so the worker knows all kinds."""

import importlib

for _module in (
    "apps.results.pipeline",
    "apps.claims.pipeline",
    "apps.alerts.pipeline",
    "apps.channels.outbox",
    "apps.voice.pipeline",
):
    try:
        importlib.import_module(_module)
    except ModuleNotFoundError as exc:  # modules arrive in later phases
        if exc.name != _module:
            raise
