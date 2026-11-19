.PHONY: smoke dev worker test check seed migrate e2e lint fmt docker-build docker-up test-pg

dev:
	sh scripts/dev.sh

worker:
	uv run python manage.py run_worker

migrate:
	uv run python manage.py migrate

seed: migrate
	uv run python manage.py seed

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

fmt:
	uv run ruff format .
	uv run ruff check --fix .

check: lint
	uv run python manage.py makemigrations --check --dry-run
	uv run pytest --cov --cov-branch --cov-report=term-missing:skip-covered --cov-fail-under=90
	uv run python scripts/secret_scan.py

e2e:
	npx playwright test

docker-build:
	docker compose build

docker-up:
	docker compose up -d
	@sleep 8; curl -fsS http://localhost:8000/healthz && echo

test-pg:
	docker compose --profile pg up -d postgres
	DATABASE_URL=postgres://votetrail:votetrail@localhost:5433/votetrail uv run pytest -m "not live"

SMOKE_PATHS ?= / /vote/?skip=1 /setup/ /verify/ /verify/?tab=rumour /activity/ /ask/ /register/ /pvc/ /accessibility/ /find/ /pu/37-06-02-002/ /pu/37-06-02-004/today/ /capture/ /pu/37-06-02-004/result/ /api/pu/37-06-02-004/result /api/me/sync /simulator/ /demo/ /dashboard/login/ /sw.js /static/css/app.css /static/js/ui.js /static/js/demo.js /static/demo/pack.json

smoke:
	SMOKE_PATHS="$(SMOKE_PATHS)" sh scripts/smoke.sh
