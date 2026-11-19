"""Azure gpt-realtime: short-lived browser sessions, and server-side voice-note understanding."""

from __future__ import annotations

import asyncio
import base64
import json
import struct
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx
from django.conf import settings

from apps.core.ai import require

from .tools import TOOL_SPECS

LANG_NAME = {"en": "English", "pcm": "Nigerian Pidgin", "yo": "Yoruba", "ha": "Hausa", "ig": "Igbo"}


def instructions(language: str) -> str:
    lang = LANG_NAME.get(language, "English")
    return f"""You are {settings.APP_NAME}, a neutral voter-help assistant for Nigerian elections.
Speak {lang}. Use short, simple sentences. Be warm and calm.
Rules:
- Every fact must come from a tool result (lookup_pu, get_result_status, check_claim, kb_search).
  If the tools don't have it, say you don't know and suggest INEC's website or local office.
- Never say who won, who will win, or who to vote for. Never give opinions about parties or
  candidates. Only INEC declares results.
- Before using a polling unit code or place the user said, read it back and ask them to confirm
  ("You said 37/06/02/004, is that right?").
- Polling unit codes have 4 parts: state/LGA/ward/unit, e.g. 37/06/02/004.
- If the user reports a rumour or incident, use check_claim and explain the status and why.
"""


def _host() -> str:
    require("AZURE_REALTIME_ENDPOINT", "AZURE_REALTIME_DEPLOYMENT", "AZURE_REALTIME_API_KEY")
    return urlparse(settings.AZURE_REALTIME_ENDPOINT).netloc


def mint_session(language: str = "en") -> dict[str, Any]:
    """Mint a short-lived client secret. The API key never leaves the server."""
    host = _host()
    body = {
        "session": {
            "type": "realtime",
            "model": settings.AZURE_REALTIME_DEPLOYMENT,
            "instructions": instructions(language),
            "tools": TOOL_SPECS,
            "tool_choice": "auto",
            "audio": {
                "output": {"voice": "marin"},
                "input": {"turn_detection": {"type": "server_vad", "silence_duration_ms": 600}},
            },
        }
    }
    resp = httpx.post(
        f"https://{host}/openai/v1/realtime/client_secrets",
        json=body,
        headers={"api-key": settings.AZURE_REALTIME_API_KEY},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        "token": data["value"],
        "expires_at": data.get("expires_at"),
        "rtc_url": f"https://{host}/openai/v1/realtime/calls",
        "model": settings.AZURE_REALTIME_DEPLOYMENT,
    }


# ---- Voice notes (server-side) ----

NOTE_INSTRUCTIONS = """Listen to the voice note. It is from a Nigerian voter and may be in English,
Nigerian Pidgin, Yoruba, Hausa or Igbo. Reply with ONLY a JSON object, no other text:
{"transcript": "<what was said, in the original language>",
 "english": "<faithful English translation>",
 "language": "en|pcm|yo|ha|ig",
 "intent": "rumour|question|other"}
intent is "rumour" when they report or forward something that happened (vote buying, violence,
late officials, missing materials, a moved polling unit); "question" when they ask for help."""


class NoteUnderstander(Protocol):
    def understand(self, pcm16: bytes) -> dict[str, Any]: ...


def wav_to_pcm16(data: bytes) -> bytes:
    """Return mono 24 kHz PCM16 samples from a WAV produced by our recorder."""
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("Expected a WAV recording.")
    pos = 12
    fmt = None
    while pos + 8 <= len(data):
        cid, size = data[pos : pos + 4], struct.unpack("<I", data[pos + 4 : pos + 8])[0]
        chunk = data[pos + 8 : pos + 8 + size]
        if cid == b"fmt ":
            fmt = struct.unpack("<HHIIHH", chunk[:16])
        elif cid == b"data":
            if fmt is None or fmt[0] != 1 or fmt[1] != 1 or fmt[2] != 24000 or fmt[5] != 16:
                raise ValueError("Recording must be 24 kHz mono 16-bit PCM.")
            return chunk
        pos += 8 + size + (size % 2)
    raise ValueError("No audio found.")


class AzureNoteUnderstander:
    async def _run(self, pcm16: bytes) -> str:
        import websockets

        url = f"wss://{_host()}/openai/v1/realtime?model={settings.AZURE_REALTIME_DEPLOYMENT}"
        async with websockets.connect(
            url,
            additional_headers={"api-key": settings.AZURE_REALTIME_API_KEY},
            max_size=None,
            open_timeout=20,
        ) as ws:
            await ws.send(
                json.dumps(
                    {
                        "type": "session.update",
                        "session": {
                            "type": "realtime",
                            "output_modalities": ["text"],
                            "instructions": NOTE_INSTRUCTIONS,
                            "audio": {
                                "input": {
                                    "format": {"type": "audio/pcm", "rate": 24000},
                                    "turn_detection": None,
                                }
                            },
                        },
                    }
                )
            )
            await ws.send(
                json.dumps(
                    {
                        "type": "conversation.item.create",
                        "item": {
                            "type": "message",
                            "role": "user",
                            "content": [
                                {"type": "input_audio", "audio": base64.b64encode(pcm16).decode()}
                            ],
                        },
                    }
                )
            )
            await ws.send(json.dumps({"type": "response.create"}))
            text = ""
            while True:
                event = json.loads(await asyncio.wait_for(ws.recv(), timeout=60))
                kind = event.get("type", "")
                if kind in ("response.output_text.delta", "response.text.delta"):
                    text += event.get("delta", "")
                elif kind == "response.done":
                    return text
                elif kind == "error":
                    raise RuntimeError(event.get("error", {}).get("message", "realtime error"))

    def understand(self, pcm16: bytes) -> dict[str, Any]:
        raw = asyncio.run(self._run(pcm16))
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0:
            raise ValueError("No transcript returned.")
        data = json.loads(raw[start : end + 1])
        if data.get("intent") not in ("rumour", "question", "other"):
            data["intent"] = "other"
        if data.get("language") not in LANG_NAME:
            data["language"] = "en"
        return data


_override: NoteUnderstander | None = None


def set_understander(u: NoteUnderstander | None) -> None:
    global _override
    _override = u


def get_understander() -> NoteUnderstander:
    return _override or AzureNoteUnderstander()
