# Kairos — working rules

Full domain model, data-source strategy, unit economics and build order live in [CONTEXT.md](CONTEXT.md). Read it before designing anything new. This file is the short enforceable version.

**Current plan and status: [.claude/ROADMAP.md](.claude/ROADMAP.md)** — PRD, milestones, task checkboxes, decision register, risk register. Check it before starting work to see what milestone we're in, and update it in the same commit as the work it tracks. Where it corrects CONTEXT.md (Part II), the roadmap wins.

## Stack

Python modular monolith. FastAPI + SQLAlchemy + PostgreSQL (JSONB for raw payloads) + Redis/Celery worker. One app process, one worker process.

**Banned:** RabbitMQ, MongoDB, microservices, a second runtime. Do not add a queue, DB, or service without saying why the existing three fail.

## Layout

```
backend/kairos/<bounded_context>/{domain,application,infrastructure,tests}/
backend/kairos/shared_kernel/          # only truly shared VOs (Money). Keep tiny.
backend/worker/                        # Celery entrypoint
```

Nine contexts: `trend_discovery`, `niche_ranking`, `creative_direction`, `content_generation`, `curation`, `listing_authoring`, `fulfillment`, `budgeting`, `analytics`.

## Dependency rule (hard)

- `domain/` — pure Python. Zero imports from `infrastructure/`, zero third-party SDKs, zero I/O. Entities, value objects, domain events, and the ports they need.
- `application/` — use cases orchestrating domain objects through ports. Ports declared in `domain/` or `application/`, never in `infrastructure/`.
- `infrastructure/` — the only layer allowed `httpx`, SQLAlchemy models, vendor SDKs. Implements ports.

Dependencies point inward only. If domain needs external data, it declares a port and infrastructure implements it.

**Cross-context:** contexts talk via application-service calls or the Celery queue. Never import another context's domain models. Never read another context's tables. Each context owns its tables.

## Compliance gates (non-negotiable — see CONTEXT.md §2)

1. **No publish without human approval.** `DraftListing` requires a prior `AssetApproved` event for that asset, enforced in the application service, not the UI. If a code path can reach Fulfillment without passing Curation, that is a bug regardless of tests passing.
2. **`AIDisclosure` is a required value object on `ListingDraft`**, not an optional field. Constructing a publishable draft without one must be structurally impossible ("Designed by", never "Made by").
3. **Phase 2:** POD listings must disclose Printful/Printify as production partner.
4. **No templated bulk generation.** Etsy detects and mass-removes it.

## Data sources

Official/sanctioned APIs only. **Never scrape Etsy or Amazon** — a scraper fingerprint correlated with the seller account risks the account, not just the session. Etsy Open API v3, TikTok Creative Center, `pytrends`, Keepa/Jungle Scout, paid vendor APIs. Adding a new source? Check CONTEXT.md §5 first.

## Naming

Ubiquitous language, matching CONTEXT.md §4 exactly. `ApproveAsset` not `UpdateStatus`. `NicheShortlisted` not `NicheUpdated`. Commands are imperative, events are past tense.

## Testing (see CONTEXT.md §8)

- Domain: pure unit tests, no mocks (nothing to mock), near-100% coverage, milliseconds.
- Application: fakes/in-memory adapters implementing real ports. No network, no DB.
- Infrastructure: recorded cassettes or a local mock server. Live API tests behind `pytest -m live_integration`, excluded from the default loop.
- Any port with 2+ adapters gets one shared contract test suite run against every adapter.
- Test names read as domain statements: `test_given_no_ai_disclosure_when_publishing_then_raises`.

## Cost

Budgeting context is wired in from day one, not later. Before any change that adds a paid API or raises generation volume, run the numbers per CONTEXT.md §6 — cost-per-*winning*-design (~20-100 generations), not cost per image.

## Open questions — ask, don't assume

Frontend framework, image-gen model, first niche, budget cap numbers. All undecided (CONTEXT.md §10). Flag rather than picking silently.
