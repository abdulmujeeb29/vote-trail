from django.core.management.base import BaseCommand

import apps.jobs.handlers  # noqa: F401  (registers all handlers)
from apps.jobs.worker import Worker


class Command(BaseCommand):
    help = "Run the background job worker."

    def add_arguments(self, parser):
        parser.add_argument("--poll", type=float, default=1.0)

    def handle(self, *args, **options):
        Worker(poll_interval=options["poll"]).run()
