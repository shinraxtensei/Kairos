# Kairos

Trend-discovery-to-Etsy-listing automation. Watches multiple platforms for rising niches, generates AI-assisted designs, routes every one through mandatory human curation, publishes approved designs as Etsy listings. Digital downloads first; print-on-demand is a Phase 2 adapter behind the same port, not a rewrite.

- **[.claude/ROADMAP.md](.claude/ROADMAP.md)** — PRD, milestones M0-M8, task tracker, decisions, risks. **Start here.**
- **[CONTEXT.md](CONTEXT.md)** — full domain model (nine bounded contexts), data-source strategy, unit economics. The reference doc.
- **[CLAUDE.md](CLAUDE.md)** — the enforceable subset: dependency rule, compliance gates, testing layers.
- **`.claude/agents/`** — `domain-architect`, `adapter-builder`, `compliance-guardian`, `test-engineer`, `economics-analyst`.

Python modular monolith: FastAPI + PostgreSQL + Redis/Celery. One app process, one worker.

## Status

**M0 — Derisk & foundations.** No code yet, by design: open the shop, prove Etsy API access and payouts, build the unit-economics model. See the roadmap.
