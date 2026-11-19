import json
from concurrent.futures import ThreadPoolExecutor

from django.core.management.base import BaseCommand, CommandError

from apps.results.evalset import EVAL_DIR, score_one, summarise
from apps.results.extract import AzureExtractor
from apps.results.imaging import clean_image


class Command(BaseCommand):
    help = "Score EC8A extraction against ground truth. --live calls Azure."

    def add_arguments(self, parser):
        parser.add_argument("--live", action="store_true")
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--report", default="")
        parser.add_argument("--workers", type=int, default=4)

    def handle(self, *args, **opts):
        if not opts["live"]:
            raise CommandError("Pass --live to call the model (costs tokens).")
        metas = sorted(EVAL_DIR.glob("ec8a_*.json"))
        if opts["limit"]:
            metas = metas[: opts["limit"]]
        if not metas:
            raise CommandError("No fixtures. Run build_ec8a_fixtures first.")
        extractor = AzureExtractor()

        def run(path):
            meta = json.loads(path.read_text())
            image = clean_image(path.with_suffix(".jpg").read_bytes())
            raw = extractor.read(
                image, {"pu_code": meta["truth"]["pu_code"]["value"], "parties": meta["parties"]}
            )
            return path.stem, score_one(raw, meta)

        with ThreadPoolExecutor(max_workers=opts["workers"]) as pool:
            results = list(pool.map(run, metas))
        summary = summarise([r for _, r in results])
        misses = [
            {"sheet": name, **row}
            for name, res in results
            for row in res["rows"]
            if not row["ok"] or row["flagged"]
        ]
        self.stdout.write(json.dumps({"summary": summary, "misses": misses}, indent=2, default=str))
        if opts["report"]:
            with open(opts["report"], "w") as fh:
                json.dump({"summary": summary, "misses": misses}, fh, indent=2, default=str)
