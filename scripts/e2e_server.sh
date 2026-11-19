#!/bin/sh
# Fresh DB, seed, then serve with Gunicorn + worker for browser tests.
set -eu
PORT=${1:-8099}
export DJANGO_SETTINGS_MODULE=votetrail.settings.e2e
rm -rf .e2e-db.sqlite3* .e2e-media
uv run python manage.py migrate --noinput -v0
uv run python manage.py seed >/dev/null
uv run python manage.py seed_demo_irev >/dev/null 2>&1 || true
uv run python manage.py collectstatic --noinput -v0 >/dev/null
uv run python manage.py run_worker --poll 0.3 &
exec uv run gunicorn votetrail.wsgi:application --bind 127.0.0.1:$PORT --workers 2 --log-level warning
