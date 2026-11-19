from unittest import mock

import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_seed_command(capsys):
    call_command("seed")
    assert "Seeded" in capsys.readouterr().out


def test_run_worker_command_uses_worker():
    with mock.patch("apps.jobs.management.commands.run_worker.Worker") as worker:
        call_command("run_worker", "--poll", "0.5")
    worker.assert_called_once_with(poll_interval=0.5)
    worker.return_value.run.assert_called_once()
