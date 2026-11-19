import json

from django.core.management.base import BaseCommand

from apps.demo.build import run_isolated


class Command(BaseCommand):
    help = "Run Amaka's scenario once through the real pipeline (live AI) and save the replay pack."

    def handle(self, *args, **opts):
        pack = run_isolated(log=lambda m: self.stdout.write(m))
        summary = {
            k: pack["steps"][k].get("status")
            if isinstance(pack["steps"][k], dict)
            else len(pack["steps"][k])
            for k in pack["steps"]
        }
        self.stdout.write(
            self.style.SUCCESS(
                f"Demo pack built in {pack['build_seconds']}s: {json.dumps(summary)}"
            )
        )
