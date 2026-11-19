from django.core.management.base import BaseCommand

from apps.elections.models import Election
from apps.jobs.queue import run_pending
from apps.results.demo_irev import seed_irev


class Command(BaseCommand):
    help = "Create labelled mock IReV sheets for the demo PUs (and read them unless --no-run)."

    def add_arguments(self, parser):
        parser.add_argument("--no-run", action="store_true")

    def handle(self, *args, **opts):
        election = Election.objects.get(slug="presidential-2027-demo")
        sheets = seed_irev(election)
        if not opts["no_run"]:
            run_pending()
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(sheets)} mock IReV sheets"))
