# Kairos

Trend-discovery-to-Etsy-listing automation. Watches multiple platforms for rising niches, generates AI-assisted designs, routes every one through mandatory human curation, publishes approved designs as Etsy listings. Digital downloads first; print-on-demand is a Phase 2 adapter behind the same port, not a rewrite.

- **[.claude/ROADMAP.md](.claude/ROADMAP.md)** — PRD, milestones M0-M8, task tracker, decisions, risks. **Start here.**
- **[CONTEXT.md](CONTEXT.md)** — full domain model (nine bounded contexts), data-source strategy, unit economics. The reference doc.
- **[CLAUDE.md](CLAUDE.md)** — the enforceable subset: dependency rule, compliance gates, testing layers.
- **`.claude/agents/`** — `domain-architect`, `adapter-builder`, `compliance-guardian`, `test-engineer`, `economics-analyst`.

Python modular monolith: FastAPI + PostgreSQL + Redis/Celery. One app process, one worker.

## Status

**M0 — Derisk & foundations** (open the shop, prove Etsy API access and payouts, build the unit-economics model) — these are account/bank/ID tasks, not code.
**M1 — Engineering skeleton** — done. See the roadmap.

## Dev setup

```bash
cd backend
uv sync --all-groups
cp .env.example .env
docker compose up -d
uv run alembic upgrade head
```

Run it:

```bash
uv run uvicorn kairos.app:app --reload
```

```bash
uv run celery -A kairos.celery_app worker --loglevel=info
```

Seed demo data (local only — fabricates assets no image model produced):

```bash
cd backend && uv run python scripts/seed_demo.py
```

| URL | What |
|---|---|
| `/review` | Review queue — the daily surface. `1`-`6` toggle IP checks, `A` approve, `R` reject, `J`/`K` navigate |
| `/niches` | Niche leaderboard |
| `/health/deep` | App + Postgres reachability |
| `/docs` | Auto-generated API reference |
| `/api/niches`, `/api/review/queue` | JSON, for a future JS frontend |

Checks — all four are what CI runs:

```bash
uv run ruff check . && uv run mypy kairos && uv run lint-imports && uv run pytest
```

`lint-imports` enforces the hexagonal dependency rule from [CLAUDE.md](CLAUDE.md). If it fails, the architecture is broken — don't silence it.
