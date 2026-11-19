#!/bin/sh
# Local production-like smoke test (no Docker): prod settings, Gunicorn + worker, real HTTP.
set -u
PORT=${SMOKE_PORT:-8077}
TMP=$(mktemp -d)
export DJANGO_SETTINGS_MODULE=votetrail.settings.prod SECURE_SSL_REDIRECT=false \
  DATABASE_URL="sqlite:///$TMP/smoke.sqlite3" MEDIA_ROOT="$TMP/media" \
  WORKER_HEARTBEAT_FILE="$TMP/hb" ALLOWED_HOSTS=localhost,127.0.0.1
uv run python manage.py collectstatic --noinput -v0 >/dev/null
uv run python manage.py migrate --noinput -v0 && uv run python manage.py seed >/dev/null
uv run gunicorn votetrail.wsgi:application --bind 127.0.0.1:$PORT --workers 2 --log-level warning &
WEB=$!
uv run python manage.py run_worker --poll 0.5 &
WORKER=$!
trap 'kill $WEB $WORKER 2>/dev/null; rm -rf "$TMP"' EXIT
FAIL=0
for i in $(seq 1 30); do curl -fsS "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1 && break; sleep 1; done
check() {
  code=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT$1")
  if [ "$code" = "$2" ]; then echo "ok   $code $1"; else echo "FAIL $code $1 (want $2)"; FAIL=1; fi
}
check /healthz 200
for path in $SMOKE_PATHS; do check "$path" 200; done
check /pu/99-99-99-999/result/ 404
[ $FAIL = 0 ] && echo "smoke: PASS" || echo "smoke: FAIL"
exit $FAIL
