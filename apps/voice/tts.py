"""ElevenLabs text-to-speech with a permanent cache (same text → same audio, one API call)."""

from __future__ import annotations

import hashlib
from typing import Protocol

import httpx
from django.conf import settings
from django.core.files.base import ContentFile

from apps.core.ai import require

from .models import TtsClip

MODEL_ID = "eleven_multilingual_v2"


class Synth(Protocol):
    def synth(self, text: str, voice_id: str) -> bytes: ...


class ElevenLabsSynth:
    def synth(self, text: str, voice_id: str) -> bytes:
        require("ELEVENLABS_API_KEY")
        resp = httpx.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            params={"output_format": "mp3_44100_64"},
            headers={"xi-api-key": settings.ELEVENLABS_API_KEY, "Accept": "audio/mpeg"},
            json={"text": text[:1000], "model_id": MODEL_ID},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.content


_override: Synth | None = None


def set_synth(s: Synth | None) -> None:
    global _override
    _override = s


def voice_for(language: str) -> str:
    voice = settings.ELEVENLABS_VOICE_ID_PCM if language == "pcm" else ""
    voice = voice or settings.ELEVENLABS_VOICE_ID_EN
    if not voice:
        require("ELEVENLABS_VOICE_ID_EN")
    return voice


def speak(text: str, language: str = "en") -> TtsClip:
    voice = voice_for(language)
    key = hashlib.sha256(f"{text}|{voice}|{MODEL_ID}".encode()).hexdigest()
    clip = TtsClip.objects.filter(key=key).first()
    if clip is not None:
        return clip
    audio = (_override or ElevenLabsSynth()).synth(text, voice)
    clip = TtsClip(key=key, text=text, voice_id=voice, model_id=MODEL_ID)
    clip.audio.save(f"{key}.mp3", ContentFile(audio), save=False)
    clip.save()
    return clip
