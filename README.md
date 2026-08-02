# Kairos

Trend-discovery-to-Etsy-listing automation. Watches multiple platforms for rising niches, generates AI-assisted designs, routes every one through mandatory human curation, publishes approved designs as Etsy listings. Digital downloads first; print-on-demand is a Phase 2 adapter behind the same port, not a rewrite.

- **[CONTEXT.md](CONTEXT.md)** — full domain model (nine bounded contexts), data-source strategy, unit economics, build order. The reference doc.
- **[CLAUDE.md](CLAUDE.md)** — the enforceable subset: dependency rule, compliance gates, testing layers.
- **`.claude/agents/`** — `domain-architect`, `adapter-builder`, `compliance-guardian`, `test-engineer`, `economics-analyst`.

Python modular monolith: FastAPI + PostgreSQL + Redis/Celery. One app process, one worker.

## Status

Pre-code. Build order starts at CONTEXT.md §7 step 1 — domain models and ports for all nine contexts, no adapters.
