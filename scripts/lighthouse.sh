#!/bin/sh
# Lighthouse (mobile) against a local production-like server. Usage: sh scripts/lighthouse.sh
set -u
PORT=8078
TMP=$(mktemp -d)
export DJANGO_SETTINGS_MODULE=votetrail.settings.prod SECURE_SSL_REDIRECT=false \
  DATABASE_URL="sqlite:///$TMP/lh.sqlite3" MEDIA_ROOT="$TMP/media" WORKER_HEARTBEAT_FILE="$TMP/hb" \
  ALLOWED_HOSTS=localhost,127.0.0.1
uv run python manage.py collectstatic --noinput -v0 >/dev/null
uv run python manage.py migrate --noinput -v0 && uv run python manage.py seed >/dev/null
uv run gunicorn votetrail.wsgi:application --bind 127.0.0.1:$PORT --workers 2 --log-level warning &
WEB=$!
trap 'kill $WEB 2>/dev/null; rm -rf "$TMP"' EXIT
sleep 3
mkdir -p docs/reviews/lighthouse
for path in / /journey/ /pu/37-06-02-002/ /pu/37-06-02-004/result/ /rumours/ /demo/; do
  name=$(echo "$path" | tr '/' '_')
  npx lighthouse "http://127.0.0.1:$PORT$path" --quiet --chrome-path="$CHROME_PATH" \
    --chrome-flags="--headless=new --no-sandbox" --form-factor=mobile \
    --only-categories=performance,accessibility,best-practices \
    --output=json --output-path="docs/reviews/lighthouse/lh$name.json" >/dev/null 2>&1
  node -e "const r=require('./docs/reviews/lighthouse/lh$name.json');const c=r.categories;console.log('$path',Object.fromEntries(Object.entries(c).map(([k,v])=>[k,Math.round(v.score*100)])))"
done
