from __future__ import annotations

import math

from django.db import models

from .codes import normalize_pu_code


class State(models.Model):
    code = models.CharField(max_length=2, unique=True)
    name = models.CharField(max_length=60)

    def __str__(self) -> str:
        return self.name


class LGA(models.Model):
    state = models.ForeignKey(State, on_delete=models.CASCADE, related_name="lgas")
    code = models.CharField(max_length=5, unique=True, help_text="SS/LL")
    name = models.CharField(max_length=80)

    class Meta:
        verbose_name = "LGA"

    def __str__(self) -> str:
        return self.name


class Ward(models.Model):
    lga = models.ForeignKey(LGA, on_delete=models.CASCADE, related_name="wards")
    code = models.CharField(max_length=8, unique=True, help_text="SS/LL/WW")
    name = models.CharField(max_length=80)

    def __str__(self) -> str:
        return self.name


class PollingUnit(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        RELOCATED = "relocated", "Relocated"
        SUSPENDED = "suspended", "Suspended"

    ward = models.ForeignKey(Ward, on_delete=models.CASCADE, related_name="polling_units")
    code = models.CharField(max_length=12, unique=True, help_text="SS/LL/WW/PPP")
    name = models.CharField(max_length=160)
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)
    coordinates_approximate = models.BooleanField(default=True)
    registered_voters = models.PositiveIntegerField(null=True, blank=True)
    accessibility_notes = models.TextField(blank=True)
    landmark = models.CharField(max_length=160, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    relocated_to = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="relocated_from"
    )
    relocated_at = models.DateTimeField(null=True, blank=True)
    source_url = models.URLField(blank=True)
    is_mock = models.BooleanField(default=False, help_text="Shown with a 'mock data' label.")

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} {self.name}"

    def save(self, *args, **kwargs) -> None:
        self.code = normalize_pu_code(self.code)
        super().save(*args, **kwargs)

    @property
    def url_code(self) -> str:
        return self.code.replace("/", "-")

    @property
    def current(self) -> PollingUnit:
        """Follow relocations to where voters should actually go."""
        pu, seen = self, set()
        while pu.status == self.Status.RELOCATED and pu.relocated_to_id and pu.pk not in seen:
            seen.add(pu.pk)
            pu = pu.relocated_to
        return pu

    def distance_m(self, lat: float, lng: float) -> float | None:
        if self.lat is None or self.lng is None:
            return None
        return haversine_m(self.lat, self.lng, lat, lng)


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
