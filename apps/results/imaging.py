"""Image handling: validate, strip EXIF, normalise, hash."""

from __future__ import annotations

import hashlib
import io

import imagehash
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 8 * 1024 * 1024
MAX_SIDE = 2000
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


class InvalidImage(ValueError):
    pass


def clean_image(data: bytes) -> bytes:
    """Return a re-encoded JPEG with no metadata (EXIF/GPS removed), max 2000px."""
    if len(data) > MAX_BYTES:
        raise InvalidImage("Photo is too large (max 8 MB).")
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()
        img = Image.open(io.BytesIO(data))
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise InvalidImage("That file isn't a photo we can read.") from exc
    if img.format not in ALLOWED_FORMATS:
        raise InvalidImage("Use a JPEG, PNG or WebP photo.")
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85, optimize=True)
    return out.getvalue()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def phash_hex(data: bytes) -> str:
    return str(imagehash.phash(Image.open(io.BytesIO(data))))
