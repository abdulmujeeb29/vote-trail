from django.core.management.base import BaseCommand

from apps.geo.seed import seed


class Command(BaseCommand):
    help = "Load the FCT polling unit sample and demo election data (idempotent)."

    def handle(self, *args, **options):
        counts = seed()
        self.stdout.write(self.style.SUCCESS(f"Seeded {counts}"))
