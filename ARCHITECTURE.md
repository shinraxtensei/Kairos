# Kairos — Architecture

How the codebase is put together and why. Read this when you want to *navigate*
the code.

Three docs, three questions:

| Doc | Answers |
|---|---|
| [CONTEXT.md](CONTEXT.md) | **Why** the business is shaped this way |
| [.claude/ROADMAP.md](.claude/ROADMAP.md) | **What** to build, in what order, what's done |
| **This file** | **How** the code is organised |

~5,000 lines of code, ~3,400 lines of tests, 8 bounded contexts, 313 tests.

---

## 1. The one-paragraph version

Kairos is a **single Python process** (plus a worker) split into **bounded
contexts** — self-contained slices of the business. Each context has three
layers with dependencies pointing strictly inward: `infrastructure → application
→ domain`. Contexts never import each other except through a **published
facade**, and there are currently exactly two such edges. All of this is
**enforced by a tool in CI**, not by discipline.

---

## 2. Why bounded contexts and not just "modules"

A module boundary you can import across isn't a boundary. Six months in, some
code needs a field from another module, imports it, and the boundary is gone —
nobody notices because nothing failed.

Kairos gets that enforcement from [import-linter](backend/pyproject.toml), which
runs in CI as its own step. Three contracts:

```
Hexagonal layers: infrastructure -> application -> domain, never reversed  KEPT
Domain layers are pure — no third-party SDKs, no I/O                       KEPT
Bounded contexts are independent                                           KEPT
```

**This has caught four real mistakes during development** — twice a context
reaching into another's repository, twice a test importing across contexts. Each
was caught by CI, not by review, and each was fixed properly rather than by
weakening the contract.

### The eight contexts

| Context | Owns | Answers |
|---|---|---|
| `trend_discovery` | trend_signals | What's rising, and where? |
| `niche_ranking` | niches | Which of those is worth pursuing? |
| `creative_direction` | style_guides | What should the designs look like? |
| `content_generation` | generated_assets | Making and processing the designs |
| `curation` | review_decisions | **Human approval — the compliance gate** |
| `listing_authoring` | listing_drafts | Assembling a compliant listing |
| `fulfillment` | listings | Publishing it, exactly once |
| `budgeting` | cost_events | What did it cost, and can we afford more? |

`analytics` (M7) isn't built — it needs traffic to learn from, and a new shop has
none for weeks.

**Each context owns its tables and nobody else reads them.** Eight tables, eight
owners, zero shared. That's the rule that makes the boundaries real at the data
layer too.

---

## 3. The three layers

Inside every context:

```
kairos/<context>/
├── domain/           pure Python — the business rules
├── application/      use cases that orchestrate the domain
├── infrastructure/   the only place I/O is allowed
└── tests/
```

### `domain/` — no I/O, no SDKs, no framework

Pure Python. It cannot import SQLAlchemy, FastAPI, Celery, httpx, pandas, or
even Kairos's own `db.py` and `config.py`. The contract enforces this by name.

This is where **business rules live as types**, so violating them is a
constructor error rather than something a code review has to catch. The clearest
examples:

```python
# Approving an asset requires a complete IP screening. Not "should" — cannot.
IpScreening(frozenset({IpCheck.NO_BRAND_NAME_OR_LOGO}), "hamid")
# ValueError: IP screening incomplete — not cleared: no_celebrity_likeness, ...

# A prompt set that varies one word is templated bulk generation. Refused.
VariationSet((serene_pastel, dreamy_pastel, calm_pastel))
# TemplatedBulkGenerationError: variations differ along only 1 axis
```

Domain code is testable with no mocks, because there is nothing to mock. Those
tests run in ~1.5 seconds for the whole suite.

### `application/` — use cases

One class per business command, named in the business's own words:
`ApproveAsset`, `RankNiches`, `PublishListing`, `DraftListing`. Never
`UpdateStatus` or `ProcessData`.

Application services take **ports** (interfaces) in their constructor and are
tested with hand-written fakes. This is where orchestration and policy decisions
live — including the compliance gate.

### `infrastructure/` — the edge

Everything that talks to the outside: SQLAlchemy models, repositories, HTTP
adapters, Celery tasks. **Vendor types never escape this layer.** An adapter
that lets an `httpx.HTTPStatusError` reach the application layer has failed at
its one job.

---

## 4. Ports and adapters, concretely

A **port** is an abstract class in `domain/`. An **adapter** implements it in
`infrastructure/`. The domain depends on the interface it defined; the concrete
thing depends on the domain. Dependencies point inward.

Current ports:

| Port | Context | Adapters |
|---|---|---|
| `TrendSource` | trend_discovery | Google Trends, eBay, Keepa *(Etsy pending)* |
| `TrendSignalRepository` | trend_discovery | SQLAlchemy |
| `TrendSignalReader` | niche_ranking | reads Trend Discovery's facade |
| `NicheRepository` | niche_ranking | SQLAlchemy |
| `ImageGenerator`, `BackgroundRemover`, `Upscaler` | content_generation | *none yet — DEC-02* |
| `ReviewDecisionRepository` | curation | SQLAlchemy |
| `ApprovalGate` | listing_authoring | reads Curation's facade |
| `FulfillmentChannel` | fulfillment | *none yet — Etsy pending* |
| `ListingRepository` | fulfillment | SQLAlchemy |
| `SpendLedgerRepository` | budgeting | SQLAlchemy |

### Why this pays off

`ImageGenerator` has **no adapter at all** and the entire pipeline above it is
built and tested. When DEC-02 is decided, one file appears in
`content_generation/infrastructure/` and nothing upstream changes. Same for
Printful in Phase 2 — it implements `FulfillmentChannel` and Listing Authoring
never learns it exists.

### Contract test suites

Any port with more than one adapter gets **one shared test suite run against
every adapter**. `TrendSource` has four registered (Google, eBay, Keepa, a fake).
Adding a fifth is one line:

```python
ADAPTERS = [
    ("google_trends", _google_adapter),
    ("ebay", _ebay_adapter),
    ("keepa", _keepa_adapter),
    ("fake", _fake_adapter),
]
```

It then must satisfy the same eight behavioural assertions as the rest. **That
is what makes "swap the adapter" actually safe** rather than merely plausible.

---

## 5. How contexts talk — the published facade

Contexts need each other's data. The naive solutions both destroy the boundary:
import the other's domain model, or read its tables.

Kairos uses a third thing: a **`public.py` at the top of the context** — a
sibling of the layers, not one of them. It's that context's composition root,
so it may wire its own application service to its own repository, and it returns
**plain DTOs only**.

```python
# kairos/curation/public.py — the entire public surface of Curation
def asset_is_approved(session: Session, asset_id: UUID) -> bool:
    return SqlAlchemyReviewDecisionRepository(session).approval_exists_for(asset_id)
```

Three contexts have one: `trend_discovery`, `curation`, `budgeting`.

**Every cross-context edge is listed by name in CI config**, so a second one
fails the build:

```toml
ignore_imports = [
    "kairos.niche_ranking.infrastructure.trend_signal_reader -> kairos.trend_discovery.public",
    "kairos.listing_authoring.infrastructure.approval_gate -> kairos.curation.public",
]
```

Two edges in the whole system. Adding a third is a review decision, not an
accident.

---

## 6. The compliance gate — the most important path in the codebase

CONTEXT.md §2 says nothing may publish without human approval. Here's how that's
actually enforced, in four independent layers:

```
1. TYPE       IpScreening cannot be constructed incomplete
                  ↓
2. AGGREGATE  ReviewDecision.__post_init__ refuses approved-without-screening
                  ↓
3. DATABASE   approval_exists_for() requires approved=true AND a screener
                  ↓
4. USE CASE   DraftListing asks the database before building anything
```

Layer 2 exists because a compliance review found layer 1 wasn't enough — the raw
constructor could produce an approved review with no screening, and the
repository rehydrating a database row would have taken exactly that path.

Layer 3 exists because `AssetApproved` is a plain dataclass **anyone can
construct**. Receiving one proves nothing. There's a test that forges one and
confirms it still doesn't unlock a draft:

```python
AssetApproved(review_id=uuid4(), asset_id=asset_id,
              reviewer="attacker", screened_by="nobody")
with pytest.raises(UnapprovedAssetError):
    draft_listing(asset_id, copy=COPY, disclosure=DISCLOSURE, pricing=PRICING)
```

**An in-memory event is a message, not a credential.** That distinction is the
whole design.

[tests/test_compliance_gate.py](backend/tests/test_compliance_gate.py) is the
single most important test file here. Six refusals, one approval.

---

## 7. Recurring patterns worth recognising

Once you see these, most of the codebase reads quickly.

### Aggregates record events, callers drain them

```python
niche.rank(signals)              # mutates, appends events
events = niche.pull_events()     # hands them over and clears
```

Draining rather than reading prevents double-publishing the same event.

### Deterministic IDs for idempotency

Anywhere a retry could duplicate something, the id is **derived**, not generated:

| What | Derived from |
|---|---|
| `TrendSignal.signal_id` | platform + keyword + observation day |
| `Niche.niche_id` | keyword |
| `Listing.listing_id` | draft id |
| Publish idempotency key | draft id |

A *generated* key is new on every retry and therefore idempotent against
nothing. `task_acks_late=True` makes Celery redelivery routine, so this isn't
theoretical — and at $0.20 per duplicate Etsy listing, it's money.

### Scale travels with the number

`SearchVolume` carries a `VolumeScale` — `ABSOLUTE` or `RELATIVE_INDEX`. Google
Trends returns a 0–100 index; eBay returns real counts; Amazon returns a rank.
A bare `int` would let ranking average `73` with `4,182` and produce a formula
that looks fine and ranks noise.

### Money is never a float

`Money` is Decimal-only and refuses floats on construction *and* multiplication.
Etsy's ~6.5% fee on sub-cent amounts is exactly where float drift would
silently corrupt the spend ledger.

### Derive, don't cache

Budget totals are **summed from stored cost events on read**, never kept as
running counters. A counter drifts the moment anything is inserted or backdated
outside the one path maintaining it — and a cap computed from a drifted counter
fails silently, in the expensive direction. It also makes period rollover free:
a new day is just a different `WHERE` clause.

### Degrade, don't halt

A failing trend source produces `TrendSourceSyncFailed` and the run continues on
the rest. A dead *database* still raises — that's not a degradation. Google
429'd for real during development and this behaved correctly.

---

## 8. The shared spine

Five files at `kairos/` root, deliberately small:

| File | Role |
|---|---|
| `app.py` | FastAPI. **Composition root** — the only place allowed to import every context |
| `celery_app.py` | Celery + beat schedule. The worker's composition root |
| `db.py` | Engine, session factory, declarative `Base` |
| `config.py` | pydantic-settings; all secrets from env |
| `observability.py` | JSON logging, correlation ids, secret redaction, `alert()` |
| `shared_kernel/money.py` | The one genuinely shared value object |

`shared_kernel` holds exactly one thing on purpose. It's where coupling goes to
hide, so it stays tiny.

---

## 9. Testing strategy

Layers map directly to test styles.

| Layer | Style | Speed |
|---|---|---|
| Domain | Pure, **zero mocks** — nothing to mock | milliseconds |
| Application | Real ports, **hand-written fakes** | milliseconds |
| Infrastructure | Stubbed HTTP / real Postgres | ~1s total |
| Cross-context | Shared `tests/` root | — |

**Fakes, not `unittest.mock`.** A fake implementing the real port breaks when
the port changes; a mock keeps passing against an interface that no longer
exists.

**Cross-context tests live in `backend/tests/`**, not inside a context —
importing two contexts from one context's tests breaks the independence
contract. That mistake was made twice and caught by CI both times.

Test names read as domain statements:

```
test_given_no_ai_disclosure_when_publishing_then_raises
test_given_a_forged_approval_event_when_drafted_then_still_refused
test_given_spend_reaching_exactly_the_cap_when_recorded_then_cap_reached
```

Tests use a **separate `kairos_test` database**. They truncate tables, and
pointing them at the dev database silently destroyed seeded data — including
leaving the last test's fixtures behind, which looks like real data.

---

## 10. Running the pipeline

```
collect (Celery, daily 06:00 UTC)
   → trend_signals
rank
   → niches  → /niches leaderboard
[generate]                          ← blocked on DEC-02
   → generated_assets
review (human, /review)             ← the compliance gate
   → review_decisions
[draft → publish]                   ← blocked on Etsy approval
   → listing_drafts → listings
```

Everything runs through `make` from the repo root — no `cd`, no remembering
`uv run`:

```bash
make setup && make seed && make dev
```

| URL | What |
|---|---|
| `/review` | Review queue — `1`–`6` toggle checks, `A` approve, `R` reject |
| `/niches` | Niche leaderboard |
| `/budget` | Spend against caps |
| `/api/*` | JSON, so a JS frontend stays possible without a rewrite |
| `/docs` | Auto-generated API reference |

---

## 11. Where to start reading

Roughly in order of how much they'll teach you:

1. **[tests/test_compliance_gate.py](backend/tests/test_compliance_gate.py)** —
   the most important behaviour, stated as assertions
2. **[curation/domain/value_objects.py](backend/kairos/curation/domain/value_objects.py)** —
   business rules as types
3. **[trend_discovery/](backend/kairos/trend_discovery/)** — the most complete
   context: domain, ports, three adapters, contract suite, facade
4. **[budgeting/domain/spend_ledger.py](backend/kairos/budgeting/domain/spend_ledger.py)** —
   authorize-before / record-after, and threshold behaviour
5. **[pyproject.toml](backend/pyproject.toml)** bottom section — the three
   contracts that hold it all together

---

## 12. Known gaps, stated plainly

- **`analytics` doesn't exist.** M7, and it needs traffic to learn from.
- **No `ImageGenerator` adapter.** DEC-02 blocks it; the port and everything
  above it are ready.
- **No `FulfillmentChannel` adapter.** Etsy approval blocks it.
- **Three tables have no repository yet** — `style_guides`, `listing_drafts`,
  `listings` have models and migrations but no mapping code.
- **`alert()` only logs CRITICAL.** There's no pager. That's honest rather than
  pretending; route it somewhere real before running unattended.
- **Budget caps are placeholders** ($2/day, $40/month) until DEC-03.
- **The review queue shows no image.** It arrives with the generator adapter.
- **ENG-38's guard only protects calls that use it.** A paid call that skips
  `metered()` isn't caught by anything. Every new paid adapter needs checking by
  hand.
