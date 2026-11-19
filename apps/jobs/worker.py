"""Long-running worker loop with heartbeat and graceful shutdown."""

from __future__ import annotations

import logging
import signal
import time
from pathlib import Path

from django.conf import settings
from django.db import close_old_connections

from .queue import claim_next, run_job

log = logging.getLogger(__name__)


class Worker:
    def __init__(self, poll_interval: float = 1.0, heartbeat: Path | None = None) -> None:
        self.poll_interval = poll_interval
        self.heartbeat = heartbeat or Path(settings.WORKER_HEARTBEAT_FILE)
        self._stop = False

    def stop(self, *_: object) -> None:
        log.info("Worker stopping after current job")
        self._stop = True

    def beat(self) -> None:
        self.heartbeat.touch()

    def run(self, max_iterations: int | None = None) -> None:
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        iterations = 0
        log.info("Worker started")
        while not self._stop:
            self.beat()
            close_old_connections()
            job = claim_next()
            if job is not None:
                run_job(job)
            else:
                time.sleep(self.poll_interval)
            iterations += 1
            if max_iterations is not None and iterations >= max_iterations:
                break
