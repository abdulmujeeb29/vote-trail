"""Azure OpenAI client factory. Fails loudly when not configured; never falls back."""

from __future__ import annotations

from functools import lru_cache

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class AIUnavailable(RuntimeError):
    pass


def require(*names: str) -> None:
    missing = [n for n in names if not getattr(settings, n, "")]
    if missing:
        raise ImproperlyConfigured(f"Missing required settings: {', '.join(missing)}")


@lru_cache(maxsize=1)
def azure_client():
    from openai import OpenAI

    require("AZURE_OPENAI_BASE_URL", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_DEPLOYMENT")
    return OpenAI(
        base_url=settings.AZURE_OPENAI_BASE_URL,
        api_key=settings.AZURE_OPENAI_API_KEY,
        timeout=90,
        max_retries=2,
    )


def structured(
    *, system: str, content: list[dict], schema: dict, name: str, max_output_tokens: int = 4000
) -> str:
    """Call the Responses API with a strict JSON schema. Returns the raw JSON text."""
    client = azure_client()
    response = client.responses.create(
        model=settings.AZURE_OPENAI_DEPLOYMENT,
        instructions=system,
        input=[{"role": "user", "content": content}],
        text={"format": {"type": "json_schema", "name": name, "schema": schema, "strict": True}},
        max_output_tokens=max_output_tokens,
    )
    text = getattr(response, "output_text", "") or ""
    if not text:
        raise AIUnavailable("Model returned no output.")
    return text
