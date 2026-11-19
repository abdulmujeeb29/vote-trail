"""Test doubles for external services."""

from __future__ import annotations

from typing import Any

from apps.results.imaging import clean_image, sha256_hex


class FakeExtractor:
    model = "fake-extractor"

    def __init__(self) -> None:
        self.by_sha: dict[str, dict[str, Any]] = {}
        self.calls = 0

    def register(self, image: bytes, raw: dict[str, Any]) -> str:
        sha = sha256_hex(clean_image(image))
        self.by_sha[sha] = raw
        return sha

    def read(self, image: bytes, context: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        return self.by_sha[sha256_hex(image)]
