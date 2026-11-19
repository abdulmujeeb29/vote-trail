#!/bin/sh
# Runs migrations, then Gunicorn + the job worker. If either exits, the container exits
# so the platform restarts it.
set -eu
python manage.py migrate --noinput
if [ "${SEED_ON_START:-0}" = "1" ]; then python manage.py seed; fi

gunicorn votetrail.wsgi:application --bind 0.0.0.0:${PORT:-8000} \
  --workers ${WEB_CONCURRENCY:-3} --timeout 60 --access-logfile - --no-control-socket &
WEB=$!
python manage.py run_worker &
WORKER=$!

trap 'kill -TERM $WEB $WORKER 2>/dev/null' TERM INT
while kill -0 $WEB 2>/dev/null && kill -0 $WORKER 2>/dev/null; do sleep 2; done
echo "A process exited; stopping container." >&2
kill -TERM $WEB $WORKER 2>/dev/null || true
wait
exit 1
