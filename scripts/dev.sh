#!/bin/sh
# One command for local dev: migrate, seed, then the web server AND the job worker together.
set -eu
PORT=${PORT:-8010}
uv run python manage.py migrate --noinput -v0
uv run python manage.py seed >/dev/null
uv run python manage.py run_worker --poll 0.5 &
WORKER=$!
trap 'kill $WORKER 2>/dev/null' EXIT INT TERM
uv run python manage.py runserver 127.0.0.1:$PORT
