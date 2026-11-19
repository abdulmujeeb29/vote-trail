from django.core.management.base import BaseCommand

from apps.results.evalset import build


class Command(BaseCommand):
    help = "Generate the synthetic EC8A evaluation set (images + ground truth)."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=32)

    def handle(self, *args, **opts):
        n = build(opts["count"])
        self.stdout.write(self.style.SUCCESS(f"Built {n} synthetic EC8A sheets"))
