# Run from anywhere in the repo. Every target cds into backend/ itself, because
# forgetting to do that produces "no configuration file provided: not found"
# from docker compose and ModuleNotFoundError from bare python.
BACKEND := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))backend
RUN := cd $(BACKEND) &&

# Tests truncate every table they touch. Pointing them at the dev database means
# `make test` silently destroys whatever you were looking at in the UI — and
# leaves the last test's fixtures behind, which is worse than empty because it
# looks like real data.
TEST_DB := postgresql+psycopg://kairos:kairos@localhost:5432/kairos_test
TEST_ENV := KAIROS_DATABASE_URL=$(TEST_DB)

# Override when 8000 is taken: make dev PORT=8001
PORT ?= 8000

.PHONY: help setup up down logs migrate migration seed dev stop worker beat check test collect rank fmt

help:  ## Show this help
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup: up migrate  ## First run: deps, services, schema
	@$(RUN) uv sync --all-groups
	@echo "Ready. 'make seed' for demo data, 'make dev' to serve."

up:  ## Start Postgres + Redis
	@$(RUN) docker compose up -d
	@$(RUN) until docker compose exec -T postgres pg_isready -U kairos >/dev/null 2>&1; do sleep 1; done
	@$(RUN) docker compose exec -T postgres psql -U kairos -d kairos \
		-c "SELECT 1 FROM pg_database WHERE datname='kairos_test'" | grep -q 1 \
		|| $(RUN) docker compose exec -T postgres createdb -U kairos kairos_test
	@echo "postgres + redis ready (dev: kairos, tests: kairos_test)"

down:  ## Stop them
	@$(RUN) docker compose down

logs:  ## Tail service logs
	@$(RUN) docker compose logs -f

migrate:  ## Apply migrations
	@$(RUN) uv run alembic upgrade head

migration:  ## Autogenerate a migration: make migration m="add x"
	@$(RUN) uv run alembic revision --autogenerate -m "$(m)"

seed:  ## Demo data for /review and /niches (local only)
	@$(RUN) uv run python scripts/seed_demo.py

dev:  ## Serve on http://localhost:$(PORT) — override with PORT=8001
	@lsof -nP -iTCP:$(PORT) -sTCP:LISTEN >/dev/null 2>&1 \
		&& echo "port $(PORT) is already in use — 'make stop' to free it, or 'make dev PORT=8001'" && exit 1 \
		|| $(RUN) uv run uvicorn kairos.app:app --reload --port $(PORT)

stop:  ## Kill a dev server left running on $(PORT)
	@pids=$$(lsof -nP -tiTCP:$(PORT) -sTCP:LISTEN 2>/dev/null); \
	if [ -n "$$pids" ]; then \
		kill $$pids 2>/dev/null; \
		for i in 1 2 3 4 5 6 7 8 9 10; do \
			lsof -nP -iTCP:$(PORT) -sTCP:LISTEN >/dev/null 2>&1 || break; sleep 0.5; \
		done; \
		echo "stopped $(PORT)"; \
	else echo "nothing on $(PORT)"; fi

worker:  ## Celery worker
	@$(RUN) uv run celery -A kairos.celery_app worker --loglevel=info

beat:  ## Celery scheduler
	@$(RUN) uv run celery -A kairos.celery_app beat --loglevel=info

collect:  ## Fetch live trend signals (hits Google Trends; 429s if repeated)
	@$(RUN) uv run python -c "from kairos.trend_discovery.infrastructure.tasks import collect_trend_signals; print(collect_trend_signals())"

rank:  ## Score niches from collected signals
	@$(RUN) uv run python -c "from kairos.niche_ranking.infrastructure.tasks import rank_niches; print(rank_niches())"

check:  ## Everything CI runs
	@$(RUN) uv run ruff check . && uv run ruff format --check . \
		&& uv run mypy kairos && uv run lint-imports && $(TEST_ENV) uv run pytest

test:  ## Tests only (against kairos_test — never touches your dev data)
	@$(RUN) $(TEST_ENV) uv run pytest

fmt:  ## Autofix lint + format
	@$(RUN) uv run ruff check --fix . && uv run ruff format .
