"""Synthetic Form EC8A generator for evaluation and demo fixtures.

Renders an EC8A-like sheet (layout per docs/ec8a-schema.md) with handwriting-style figures,
then applies realistic damage (skew, blur, shadow, noise, smudge). Every image ships with a
ground-truth JSON in the same shape the model must return. Clearly synthetic: the header
says "SPECIMEN".
"""

from __future__ import annotations

import io
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from django.conf import settings
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .words import int_to_words

FONTS = Path(settings.BASE_DIR) / "fixtures" / "fonts"
W, H = 1240, 1754  # A4 at 150 dpi


@dataclass
class SheetSpec:
    pu_code: str
    pu_name: str
    ward: str
    lga: str
    state: str = "FCT"
    election: str = "PRESIDENTIAL"
    parties: dict[str, int] = field(default_factory=dict)
    registered: int = 900
    accredited: int | None = None
    rejected: int = 9
    ballots_issued: int | None = None
    spoilt: int = 1
    cancelled: bool = False
    override_total_valid: int | None = None  # to create arithmetic errors
    smudge: str | None = None  # field to make unreadable, e.g. "party:PB" or "rejected"
    seed: int = 0
    damage: str = "light"  # none | light | heavy

    @property
    def total_valid(self) -> int:
        return (
            self.override_total_valid
            if self.override_total_valid is not None
            else sum(self.parties.values())
        )

    @property
    def total_used(self) -> int:
        return sum(self.parties.values()) + self.rejected

    def totals(self) -> dict[str, int]:
        accredited = self.accredited if self.accredited is not None else self.total_used + 3
        issued = self.ballots_issued if self.ballots_issued is not None else self.registered
        unused = issued - self.total_used - self.spoilt
        return {
            "registered": self.registered,
            "accredited": accredited,
            "ballots_issued": issued,
            "unused": unused,
            "spoilt": self.spoilt,
            "rejected": self.rejected,
            "total_valid": self.total_valid,
            "total_used": self.total_used,
        }


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), size)


def _print(size: int) -> ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def _hand(rnd: random.Random, size: int) -> ImageFont.FreeTypeFont:
    return _font(rnd.choice(["Caveat.ttf", "Kalam-Regular.ttf"]), size)


def truth(spec: SheetSpec) -> dict[str, Any]:
    def f(value, unreadable=False):
        return {
            "value": None if unreadable else value,
            "confidence": 0.0 if unreadable else 1.0,
            "unreadable": unreadable,
        }

    totals = spec.totals()
    data: dict[str, Any] = {
        "pu_code": f(spec.pu_code),
        "pu_name": f(spec.pu_name),
        "ward": f(spec.ward),
        "lga": f(spec.lga),
        "state": f(spec.state),
        "election": f(spec.election),
        "cancelled": f(spec.cancelled),
        "signed_by_agents": f(True),
        "stamped": f(True),
    }
    for k, v in totals.items():
        data[k] = f(v, spec.smudge == k)
    data["parties"] = [
        {
            "party": p,
            "figures": f(v, spec.smudge == f"party:{p}"),
            "words": f(int_to_words(v), spec.smudge == f"party:{p}"),
        }
        for p, v in spec.parties.items()
    ]
    return data


def render(spec: SheetSpec) -> bytes:
    rnd = random.Random(spec.seed)
    img = Image.new("RGB", (W, H), (246, 244, 236))
    d = ImageDraw.Draw(img)
    ink = (28, 38, 120)
    black = (25, 25, 25)

    d.text(
        (W // 2, 60),
        "INDEPENDENT NATIONAL ELECTORAL COMMISSION",
        font=_print(34),
        fill=black,
        anchor="mm",
    )
    d.text(
        (W // 2, 105),
        f"FORM EC8A · {spec.election} ELECTION · SPECIMEN",
        font=_print(26),
        fill=black,
        anchor="mm",
    )
    d.text(
        (W // 2, 140),
        "STATEMENT OF RESULT OF POLL FROM POLLING UNIT",
        font=_print(22),
        fill=black,
        anchor="mm",
    )
    y = 200
    for label, value in [
        ("State", spec.state),
        ("LGA", spec.lga),
        ("Registration Area/Ward", spec.ward),
        ("Polling Unit", spec.pu_name),
        ("PU Code", spec.pu_code),
    ]:
        d.text((80, y), f"{label}:", font=_print(22), fill=black)
        d.text((420, y - 8), value, font=_hand(rnd, 40), fill=ink)
        d.line((410, y + 28, W - 80, y + 28), fill=(150, 150, 150), width=1)
        y += 52

    y += 20
    labels = [
        ("registered", "1. Number of Voters on the Register"),
        ("accredited", "2. Number of Accredited Voters"),
        ("ballots_issued", "3. Number of Ballot Papers Issued to the PU"),
        ("unused", "4. Number of Unused Ballot Papers"),
        ("spoilt", "5. Number of Spoilt Ballot Papers"),
        ("rejected", "6. Number of Rejected Ballots"),
        ("total_valid", "7. Total Number of Valid Votes"),
        ("total_used", "8. Total Number of Used Ballot Papers"),
    ]
    totals = spec.totals()
    boxes: dict[str, tuple[int, int, int, int]] = {}
    for key, label in labels:
        d.rectangle((70, y - 6, W - 70, y + 44), outline=(120, 120, 120), width=1)
        d.text((86, y + 6), label, font=_print(22), fill=black)
        x = W - 330 + rnd.randint(-6, 6)
        d.text((x, y - 6 + rnd.randint(-3, 3)), str(totals[key]), font=_hand(rnd, 46), fill=ink)
        boxes[key] = (W - 340, y - 6, W - 70, y + 44)
        y += 56

    y += 24
    d.text(
        (80, y),
        "S/N   Political Party      Votes (Figures)        Votes (Words)",
        font=_print(22),
        fill=black,
    )
    y += 40
    for i, (party, votes) in enumerate(spec.parties.items(), start=1):
        d.rectangle((70, y - 6, W - 70, y + 52), outline=(120, 120, 120), width=1)
        d.text((86, y + 10), f"{i}.", font=_print(22), fill=black)
        d.text((160, y + 10), party, font=_print(26), fill=black)
        d.text((430 + rnd.randint(-5, 5), y - 6), str(votes), font=_hand(rnd, 48), fill=ink)
        d.text((640, y + 2), int_to_words(votes), font=_hand(rnd, 34), fill=ink)
        boxes[f"party:{party}"] = (420, y - 6, W - 70, y + 52)
        y += 62

    y += 40
    d.text((80, y), "Agents' signatures:", font=_print(22), fill=black)
    for i in range(len(spec.parties)):
        sx = 360 + i * 200
        d.line((sx, y + 20, sx + 140, y + 4 + rnd.randint(-8, 8)), fill=ink, width=3)
    d.ellipse((W - 330, y + 70, W - 130, y + 250), outline=(140, 30, 30), width=5)
    d.text(
        (W - 230, y + 160),
        "INEC\nPO STAMP",
        font=_print(22),
        fill=(140, 30, 30),
        anchor="mm",
        align="center",
    )

    if spec.cancelled:
        stamp = Image.new("RGBA", (900, 160), (0, 0, 0, 0))
        ImageDraw.Draw(stamp).text(
            (450, 80), "RESULT CANCELLED", font=_print(96), fill=(200, 20, 20, 210), anchor="mm"
        )
        stamp = stamp.rotate(18, expand=True)
        img.paste(stamp, (150, 800), stamp)

    if spec.smudge and spec.smudge in boxes:
        x0, y0, x1, y1 = boxes[spec.smudge]
        blob = Image.new("RGBA", img.size, (0, 0, 0, 0))
        bd = ImageDraw.Draw(blob)
        for _ in range(18):
            cx, cy = rnd.randint(x0, min(x1, x0 + 360)), rnd.randint(y0, y1)
            r = rnd.randint(18, 40)
            bd.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(40, 45, 110, 235))
        img = Image.alpha_composite(img.convert("RGBA"), blob.filter(ImageFilter.GaussianBlur(4)))
        img = img.convert("RGB")

    img = _damage(img, rnd, spec.damage)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=88)
    return out.getvalue()


def _damage(img: Image.Image, rnd: random.Random, level: str) -> Image.Image:
    if level == "none":
        return img
    angle = rnd.uniform(-2.5, 2.5) if level == "light" else rnd.uniform(-6, 6)
    img = img.rotate(angle, expand=True, fillcolor=(60, 60, 60))
    shadow = Image.new("L", img.size, 0)
    sd = ImageDraw.Draw(shadow)
    sd.rectangle(
        (0, 0, int(img.width * rnd.uniform(0.2, 0.5)), img.height),
        fill=60 if level == "light" else 110,
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(80))
    dark = Image.new("RGB", img.size, (0, 0, 0))
    img = Image.composite(dark, img, shadow)
    if level == "heavy":
        img = img.filter(ImageFilter.GaussianBlur(1.3))
    noise = Image.effect_noise(img.size, 18 if level == "light" else 32).convert("RGB")
    img = Image.blend(img, noise, 0.06 if level == "light" else 0.1)
    return img.resize((int(img.width * 0.9), int(img.height * 0.9)))
