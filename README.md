# Kairos

Trend-discovery-to-Etsy-listing automation. Watches multiple platforms for rising niches, generates AI-assisted designs, routes every one through mandatory human curation, publishes approved designs as Etsy listings. Digital downloads first; print-on-demand is a Phase 2 adapter behind the same port, not a rewrite.

- **[ARCHITECTURE.md](ARCHITECTURE.md)** — how the code is organised: contexts, layers, ports, the compliance gate, recurring patterns. Read this to navigate the codebase.
- **[.claude/ROADMAP.md](.claude/ROADMAP.md)** — PRD, milestones M0-M8, task tracker, decisions, risks. **Start here.**
- **[CONTEXT.md](CONTEXT.md)** — full domain model (nine bounded contexts), data-source strategy, unit economics. The reference doc.
- **[CLAUDE.md](CLAUDE.md)** — the enforceable subset: dependency rule, compliance gates, testing layers.
- **`.claude/agents/`** — `domain-architect`, `adapter-builder`, `compliance-guardian`, `test-engineer`, `economics-analyst`.

Python modular monolith: FastAPI + PostgreSQL + Redis/Celery. One app process, one worker.

## Status

**M0 — Derisk & foundations** (open the shop, prove Etsy API access and payouts, build the unit-economics model) — these are account/bank/ID tasks, not code.
**M1 — Engineering skeleton** — done. See the roadmap.

## Dev setup

Everything runs through `make` from the repo root — no `cd`, no remembering `uv run`:

```bash
make setup
```

```bash
make seed
```

```bash
make dev
```

| URL | What |
|---|---|
| `/review` | Review queue — the daily surface. `1`-`6` toggle IP checks, `A` approve, `R` reject, `J`/`K` navigate |
| `/niches` | Niche leaderboard |
| `/health/deep` | App + Postgres reachability |
| `/docs` | Auto-generated API reference |
| `/api/niches`, `/api/review/queue` | JSON, for a future JS frontend |

`make help` lists everything. The ones you'll want: `check` (everything CI runs), `test`, `fmt`, `worker`, `collect`, `rank`, `down`.

`lint-imports` enforces the hexagonal dependency rule from [CLAUDE.md](CLAUDE.md). If it fails, the architecture is broken — don't silence it.

When something breaks in production, [.claude/RUNBOOK.md](.claude/RUNBOOK.md).
