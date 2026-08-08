# Run from anywhere in the repo. Every target cds into backend/ itself, because
# forgetting to do that produces "no configuration file provided: not found"
# from docker compose and ModuleNotFoundError from bare python.
BACKEND := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))backend
RUN := cd $(BACKEND) &&

.PHONY: help setup up down logs migrate migration seed dev worker beat check test collect rank fmt

help:  ## Show this help
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup: up migrate  ## First run: deps, services, schema
	@$(RUN) uv sync --all-groups
	@echo "Ready. 'make seed' for demo data, 'make dev' to serve."

up:  ## Start Postgres + Redis
	@$(RUN) docker compose up -d
	@$(RUN) until docker compose exec -T postgres pg_isready -U kairos >/dev/null 2>&1; do sleep 1; done
	@echo "postgres + redis ready"

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

dev:  ## Serve on http://localhost:8000
	@$(RUN) uv run uvicorn kairos.app:app --reload

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
		&& uv run mypy kairos && uv run lint-imports && uv run pytest

test:  ## Tests only
	@$(RUN) uv run pytest

fmt:  ## Autofix lint + format
	@$(RUN) uv run ruff check --fix . && uv run ruff format .
