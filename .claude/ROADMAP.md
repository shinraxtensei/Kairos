# Kairos — PRD & Roadmap

**Status doc. Update it as work lands.** This is the single tracker for the whole project — business, legal, ops, and code. `CONTEXT.md` is the reference (why things are shaped this way); this is the plan (what to do, in what order, and whether it's done).

Last reviewed: 2026-08-02

---

## Status legend

| Mark | Meaning |
|---|---|
| `[ ]` | Not started |
| `[~]` | In progress |
| `[x]` | Done |
| `[!]` | Blocked — the `Note:` must say by what |
| `[-]` | Dropped / deliberately skipped — the `Note:` must say why |

Every task that is `[x]` with caveats keeps a `Note:` line. Example:

```
- [x] **ENG-12** Etsy publish adapter
      Note: done, but no idempotency key yet — a retry double-lists at $0.20 each. ENG-13 covers it.
```

Task IDs are stable. Never renumber; if a task dies, mark `[-]` and leave it.

---

# Part I — PRD

## 1. Problem

Finding a profitable Etsy niche and shipping listings into it is a manual, slow, taste-driven loop: watch trends, guess a niche, design something, write the listing, publish, wait. The bottleneck is not design skill — it's **timing and throughput**. By the time a human notices a niche is rising, it's usually saturated.

## 2. Product

Kairos compresses that loop: it watches sanctioned trend sources, scores niches on profitability-vs-competition, generates AI-assisted design candidates, routes every candidate through a **mandatory human curation gate**, and publishes approved designs as Etsy listings. Digital downloads first; print-on-demand is a Phase 2 adapter behind the same port.

The human stays in the loop on the one thing humans are actually better at — taste and legal judgment — and is removed from everything else.

## 3. Goals

| # | Goal | Measure |
|---|---|---|
| G1 | Real income, worldwide, from near-zero capital | First $1 of revenue; then first month where revenue > costs |
| G2 | Compress niche-to-listing cycle time | < 24h from `NicheShortlisted` to `ListingPublished` |
| G3 | Never risk the shop | Zero IP strikes, zero AI-disclosure violations, zero ToS-triggered suspensions |
| G4 | Know the unit economics | Cost-per-*winning*-listing is a measured number, not an estimate |

## 4. Non-goals (v1)

- Not a multi-tenant SaaS. One shop, one operator. No Etsy Commercial API access needed.
- Not a marketplace-agnostic platform. Etsy first; the ports exist so Phase 2 POD is cheap, not because other marketplaces are planned.
- Not ML-ranked. A weighted formula until it demonstrably fails.
- Not a React app until the review queue actually needs React.
- Not fully autonomous. The curation gate is permanent, not a training-wheel.

## 5. Success metrics

| Metric | Target | When |
|---|---|---|
| Trend sources live | 3 (Etsy, Google Trends, TikTok) | M2 |
| Time niche → published listing | < 24h | M5 |
| Curation throughput | 50 assets reviewed in < 15 min | M4 |
| Cost per generated design | < $0.12 | M4 |
| Cost per **winning** design | measured, then < 40% of that listing's 90-day revenue | M7 |
| Listing→view rate | benchmark first, then improve | M7 |
| IP / disclosure strikes | **0** | always |

## 6. Constraints

- **Solo operator.** Every hour of ops burden is an hour not building. Prefer boring.
- **Near-zero capital, rent-paying timeline.** Recurring cost is the enemy; a $50/mo subscription must earn its place.
- **One runtime (Python), one DB (Postgres), one broker (Redis).** See CONTEXT.md §3.1.
- **Etsy compliance is a hard gate, not a feature.** A shop suspension ends the project, not a sprint.

## 7. Reality check on timeline

A new Etsy shop gets close to zero organic traffic for the first several weeks regardless of listing quality. **The system can be technically perfect and still show $0 for a month.** Plan cash accordingly, and do not read early silence as a product failure — G1's first milestone is *first dollar*, not *replacement income*.

Consequence for the build: the Analytics feedback loop (M7) is worthless until there is traffic to learn from. It is sequenced last on purpose. Do not let it block M5.

---

# Part II — Senior review of CONTEXT.md

Findings from reviewing the constitution against how Etsy and the vendors actually behave. **These change the plan; they are not nitpicks.**

## R1 — The build order is inverted (highest-impact change)

CONTEXT.md §7 step 1 says "domain models + ports for all nine contexts — no adapters yet." That is weeks of modeling before a single fact about the real world is validated, and the model will be wrong in the places that matter because nothing has pushed back on it yet.

**Change:** derisk the business gates first (M0 — days, no code), then model **only the contexts in the current vertical slice**. Domain-first *per slice*, not domain-first *for all nine*. The DDD discipline is preserved; the speculative modeling is not. `creative_direction`, `analytics` and `budgeting` get modeled when they're built, and by then you'll know things about them you don't know today.

## R2 — Four gaps in the domain model

CONTEXT.md §4 covers nine contexts and misses four concerns. Two of them are shop-killers.

| Gap | Why it matters | Where it goes |
|---|---|---|
| **IP / trademark screening** | Etsy operates DMCA takedowns without investigating. Strikes accumulate; a *pattern* of infringement means permanent suspension, and you're liable for a design you didn't know was infringing. This is the single most likely way to lose the shop, and it appears nowhere in the model. | New blocking step in **Curation** — see CMP-04 |
| **Asset packaging / delivery** | Etsy digital listings allow **5 files, 20MB each, filenames ≤70 chars**. A 300-DPI print-ready PNG blows past 20MB routinely. There is currently no step between "approved asset" and "file Etsy will accept." | New concern in **Content Generation** or a thin `asset_delivery` module — see ENG-24 |
| **Listing SEO copy** | Etsy titles + 13 tags are the entire traffic mechanism. `ListingDraft` currently has pricing and disclosure and no title/tags/description. Without this you publish invisible listings — technically compliant, commercially dead. | **Listing Authoring** — see ENG-26 |
| **Publish idempotency** | $0.20 per listing, non-refundable. A retry or a redelivered Celery task double-lists. | **Fulfillment** — see ENG-28 |

## R3 — FLUX.1 [dev] cannot be used

`FLUX.1 [dev]` is under a **non-commercial license** — it's the variant everyone self-hosts, and selling its output violates the license. Only `FLUX.1 [schnell]` (Apache 2.0) or `FLUX.1 [pro]` (BFL API, commercial terms, usage reported through the API) are usable here. Whichever model wins the M4 bake-off, **the license is a selection criterion, not an afterthought** — check Midjourney's commercial terms and the Gemini/"Banana" terms the same way. See DEC-02.

## R4 — Etsy API access ~~is a smaller risk than it looks~~ **CORRECTED 2026-08-08**

**The original claim here was wrong and is retracted.** It said access "is approved in minutes with no manual review queue." It is not.

**Personal Access is manually reviewed by Etsy.** The app sits at *Pending Personal Approval* and **the keystring does not work until approved** — Etsy's quickstart states approval is a prerequisite. Typical turnaround is 24-48h, but community reports run from several days to about three weeks, with no SLA and no progress visibility. Commercial Access (apps other sellers connect to) is a deeper review still, and remains a **non-goal**.

Actual granted limits: **5 QPS / 5,000 per day** — half the documented default, normal for a new app, and still ample (see ENG-04).

**Consequences:**
- M0 cannot be "finished in days" on the API side. It is finished when Etsy says so.
- ENG-02, ENG-03 and ENG-18 are blocked on a queue nobody controls — see RSK-12.
- **This is the argument for M3.** Running the loop by hand needs no API at all, so the wait is not idle time. If the approval lands quickly, M3 was worth doing anyway; if it takes three weeks, M3 is the difference between three lost weeks and three useful ones.

## R5 — TikTok Creative Center is not as clean as claimed

CONTEXT.md §5 calls it "official, zero scraping." The public Creative Center is a **web UI**; pulling its data programmatically means calling undocumented internal JSON endpoints. That is lower-risk than scraping Etsy (no seller account is tied to it, so the §5 account-correlation logic doesn't apply) but it is **not** a sanctioned API, and it will break without notice.

**Change:** treat it as best-effort. It must never be on the critical path — if the adapter breaks, the pipeline degrades to Etsy + Google Trends and carries on. Same caveat for `pytrends`, which is unofficial and breaks whenever Google changes its endpoints. **Neither may be a hard dependency.** See ENG-17.

## R6 — Curation UI is a real product, and the throughput math is unforgiving

CONTEXT.md §4.5 correctly calls the review queue "the actual product surface." Take that literally: at ~1-5% winners, reviewing enough designs to find winners means reviewing *a lot* of designs. If review takes 10 seconds per asset instead of 2, that is the binding constraint on the entire business — not generation cost, not API limits.

Design it keyboard-first (J/K/A/R), one asset per screen, no mouse. This is why FastAPI + HTMX beats a React SPA here (DEC-01).

## R7 — Everbee/eRank have no public API

They are browser tools. Their data enters via **manual CSV export**, not an adapter. Budget for that as an operator ritual, not an integration. Do not build a scraper for them.

---

# Part III — Milestones

Each milestone has an exit criterion. Don't start the next one until it's met.

---

## M0 — Derisk & foundations

**Exit criterion:** an Etsy shop exists, API credentials work against it, and the unit-economics model says this can be profitable.
**No code in this milestone.** Days, not weeks. Every item here can kill or reshape the project — find out now.

### Business & accounts

- [ ] **BIZ-01** Confirm seller country is Etsy Payments–eligible, and whether it's direct or Payoneer-routed. Requires a residential address + bank account in that country.
      Note: Morocco appears on the eligible list — **verify on Etsy's own help page before relying on it**, the list changes.
- [ ] **BIZ-02** Decide seller entity: individual vs registered business. Affects tax ID, invoicing, and Etsy Payments enrollment.
      Note:
- [ ] **BIZ-03** Open the Etsy shop. Complete ID verification and bank/payout setup end to end.
      Note:
- [ ] **BIZ-04** Confirm payouts actually land — make one real sale (even to yourself via a friend) and watch the money arrive.
      Note: don't skip. "Shop opened" and "money reaches my bank" are different facts.
- [ ] **BIZ-05** Set up a dedicated business email + password manager entry for all Kairos accounts.
      Note:
- [ ] **BIZ-06** Open a separate bank account or sub-account for the business.
      Note: mixing personal and business cashflow makes ENG-40's economics unmeasurable.

### API access

- [~] **ENG-01** Register the Etsy app, request Personal Access (own shop only — not Commercial).
      Note: app "kairos" registered 2026-08-08, keystring issued, **status: Pending Personal Approval**. Contrary to what R4 originally claimed, this is a **manual review** and the keystring does not work until it clears — typically 24-48h, sometimes ~3 weeks. If it passes a week, nudge via Etsy's [API help form](https://developers.etsy.com/documentation/get-help/). Keys are in local `.env`.
- [!] **ENG-02** Complete Etsy OAuth 2.0 PKCE flow by hand once; store the refresh token. Confirm access-token refresh works.
      Note: **blocked on ENG-01 approval** — OAuth cannot succeed with an unapproved keystring. Everything on our side is ready: `scripts/etsy_oauth.py` is written and its PKCE generation verified against RFC 7636. Still to do when approval lands: register an HTTPS callback URL on the app, then run the script. The PKCE flow needs only the keystring — **the shared secret is unused by Kairos.** The refresh token expires after 90 days of disuse and is the secret worth protecting.
- [!] **ENG-03** Call `getShop` and `createDraftListing` manually against the real shop. Delete the draft after.
      Note: **blocked on ENG-02.** Proves credentials + scopes before any abstraction is written.
- [x] **ENG-04** Confirm rate limits on the account (expect 10 QPS / 10k per day).
      Note: **actual is 5 QPS / 5,000 per day** — half the documented default, which is normal for a new app and raisable on request. Still ample: trend discovery (~100/day at 50 seeds) plus publishing (~120/day at 10 listings × ~10 calls) leaves ~4,700/day for Analytics polling, and `getShopListingsActive` pages 100 at a time. Thousands of listings before this binds. **Etsy's limits are not a throughput ceiling for this project** — curation review speed (RSK-07) and Google's 429s are.

### Economics

- [ ] **BIZ-07** Build the unit-economics spreadsheet — CONTEXT.md §6. Inputs: cost/image, variations per design, images per winner (20-100), listing fee $0.20, ~6.5% transaction fee, payment processing, monthly subscriptions.
      Note: this is the blocker for every budget cap number. Nothing in M6 can be set without it.
- [ ] **BIZ-08** Model three scenarios: 1% / 3% / 5% winner rate. Note where the conclusion flips.
      Note:
- [ ] **BIZ-09** Set the initial monthly all-in ceiling. This becomes `BudgetLimit`'s real value.
      Note:

### Compliance groundwork

- [ ] **CMP-01** Read Etsy's Creativity Standards and the AI-disclosure policy in full, from Etsy's own site.
      Note: enforcement began **2026-01-14**; ~12,000 listings removed and ~8,500 warnings issued in Q1 2026. Removal can come with no warning.
- [ ] **CMP-02** Write the exact AI-disclosure copy to be used on every listing, and where it goes (attribution field + description).
      Note: "Designed by", never "Made by".
- [ ] **CMP-03** Read Etsy's IP policy and the DMCA takedown/counter-notice process.
      Note:
- [ ] **CMP-04** Write the **IP screening checklist** for the curation gate — no brand names, logos, characters, celebrity likeness, sports teams, song lyrics, or trademarked phrases. Include how to check a phrase against USPTO TESS.
      Note: gap found in review (R2). This is the highest-probability shop-killer.

**M0 exit:** BIZ-03, BIZ-04, ENG-03, BIZ-07 all `[x]`.

---

## M1 — Engineering skeleton

**Exit criterion:** `pytest` runs green in CI, a Celery task executes end to end locally, and the app boots.

- [x] **ENG-05** `backend/` scaffold per CONTEXT.md §3.2. `pyproject.toml`, uv or Poetry, Python 3.12+.
      Note: uv, pinned to 3.12 via `.python-version`. uv defaulted to 3.14, which disagreed with the mypy/ruff target — pinned so all three match. Only `trend_discovery` and `niche_ranking` packages exist; the other seven get created when built, so a missing package is a typo rather than an unenforced context.
- [x] **ENG-06** Ruff + mypy (strict on `domain/`), pre-commit hooks.
      Note: ruff + mypy done, enforced in CI. **Pre-commit hooks deliberately skipped** — CI is the gate and a second enforcement point is maintenance for no extra safety. Add locally if the feedback loop feels slow.
- [x] **ENG-07** **Import-linter contract enforcing the dependency rule** — `domain` may not import `infrastructure`; no cross-context domain imports.
      Note: 3 contracts (layers / domain-purity / context-independence). **Verified by deliberately breaking each one** — a green result on empty packages proves nothing, so both violations were introduced, caught, and reverted. `include_external_packages = true` is required for the domain-purity contract to name third-party packages.
- [x] **ENG-08** Postgres + Redis via docker-compose for local dev.
      Note: postgres:17-alpine, redis:7-alpine, both with healthchecks. Verified up and healthy.
- [x] **ENG-09** Alembic wired up, first empty migration.
      Note: sync template (the engine is sync — the async template was wrong and was redone). URL comes from `Settings`, not `alembic.ini`, so no credentials sit in a committed file. Baseline `117dac0d6a22` applied against real Postgres and confirmed in `alembic_version`. **`migrations/env.py` needs each context's models imported as they are built** or autogenerate silently emits empty migrations.
- [x] **ENG-10** Celery worker + beat, one hello-world periodic task proving the loop.
      Note: worker round-trip verified end to end (`ping` → `pong` over Redis). **No beat schedule yet** — there is no periodic task to schedule until ENG-22. `task_acks_late=True` is set, which means redelivery on worker loss is normal operation and makes ENG-34's publish idempotency load-bearing rather than theoretical.
- [x] **ENG-11** Settings via pydantic-settings, `.env` for secrets, `.env.example` committed.
      Note: `KAIROS_` env prefix. `.env.example` has the Etsy credential slots commented out ready for ENG-02.
- [x] **ENG-12** FastAPI app skeleton + `/health`.
      Note: plus `/health/deep`, which checks Postgres reachability and degrades rather than raising. A shallow health check that returns ok while the DB is down is how OPS-04 misses an outage.
- [x] **ENG-13** GitHub Actions: ruff, mypy, pytest (excluding `live_integration`).
      Note: five steps — lint, format, types, **architecture**, tests. `lint-imports` runs as its own step so a dependency-rule breach reads as an architecture failure, not a lint failure.
- [x] **ENG-14** `shared_kernel` with `Money` only. Resist adding to it.
      Note: Decimal-only, rejects float on both construction and multiplication, ROUND_HALF_UP, refuses cross-currency arithmetic. Etsy's ~6.5% fee on sub-cent amounts is exactly where float would quietly corrupt the `SpendLedger`.
- [x] **TST-01** pytest layout + markers (`live_integration`), fake-adapter conventions per CONTEXT.md §8.
      Note: marker registered and excluded from the default run via `addopts`; `--strict-markers` on. 14 tests, ~0.7s. **Fake-adapter conventions not written yet** — deferred to M2, where the first real port exists to write them against. Writing them now would be guessing.

**M1 exit:** ✅ ENG-07 and ENG-13 green. Full local run: ruff clean, mypy clean, 3/3 contracts kept, 14 tests pass, migrations apply.

Known minor: `starlette.testclient` warns that httpx support is deprecated in favour of httpx2. Cosmetic; left alone rather than churning a working dev dependency.

---

## M2 — Trend discovery → niche ranking (first vertical slice)

**Exit criterion:** a scheduled job pulls real signals from ≥2 sources and produces a ranked niche leaderboard you'd actually act on.

### Domain

- [x] **ENG-15** `trend_discovery` domain: `TrendSignal` aggregate, `SourcePlatform`, `Keyword`, `SearchVolume`, `CompetitionLevel`, `CollectedAt`. `TrendSource` port.
      Note: **`SearchVolume` carries a `VolumeScale`** (ABSOLUTE vs RELATIVE_INDEX). Google Trends returns a 0-100 index and Etsy returns absolute counts; a bare int would let ranking average 73 with 4,182 and produce confident noise. `CompetitionLevel.from_competing_listings` keeps the threshold ladder in the domain so every source maps through the same rule — **retune those bands once M7 shows which ones correlate with sales.**
- [x] **ENG-16** `niche_ranking` domain: `Niche`, `ProfitabilityScore`, `RankingCriteria`. Events: `NicheScored`, `NicheShortlisted`, `NicheRejected`.
      Note: weighted formula, explainable, weights validated to sum to 1.0. `ScoreBreakdown` records every component and the applied weights so a score can be argued with later — a formula whose reasoning was not recorded cannot be tuned.
      Two decisions worth revisiting: **missing signals renormalise the remaining weights** rather than counting as zero (momentum 80 alone scores 80, not 24 — otherwise every niche looks terrible whenever a source is down), and `ProfitabilityScore` carries a **`Confidence`** derived from how many signals were present. `Niche.needs_corroboration` flags a shortlist built on one source. **Until ENG-18 lands, every niche is in that state** — treat the leaderboard as momentum-only and do not commit design spend off it (RSK-04).
      Not yet done for this context: persistence, application service, and the cross-context edge that turns `TrendSignal`s into `NicheSignals`. `demand_reference` (10,000) is a placeholder — set it from real Etsy result counts, and switch demand to a log scale if counts span orders of magnitude.

### Adapters

- [x] **ENG-17** Adapter resilience policy: a failing trend source degrades the pipeline, never halts it. `TrendSourceSyncFailed` + alert, pipeline continues on remaining sources.
      Note: two failure paths covered — a translated `TrendSourceError`, and an adapter that leaks a raw vendor exception (a bug in that adapter, but it must not take the run down). A dead *database* still raises, because that is not a degradation. **Validated for real:** a live run hit Google's 429 and degraded exactly as designed.
- [!] **ENG-18** `EtsyTrendAdapter` (Open API v3 search/taxonomy).
      Note: **blocked on ENG-01/02** (Etsy API credentials from M0). Port, contract suite and `SourcePlatform.ETSY` are all in place, so this is an adapter drop-in when the keys exist.
- [x] **ENG-19** `GoogleTrendsAdapter` (`pytrends`).
      Note: works against the live API. Three real behaviours handled: the final row is `isPartial` (an incomplete period that reads as a collapse and would drag momentum down on exactly the rising keywords we hunt); **one term per request** (see below); and a 2s inter-request delay because Google 429s readily. Signal ids are `uuid5(platform, keyword, observation-day)` so redelivery cannot duplicate a row.
      **Bug found in a live run:** Google rescales its 0-100 index *within a batch*, so `moon phase print` scored **1** beside `cat sticker` — not low interest, just a shared request. Fetching one term per request makes the index relative to that keyword's own history (`8` for the same keyword — an 8× distortion). **Google Trends is the momentum source; Etsy supplies absolute demand.** Costs one request per seed; the delay default is a guess — tune it against real seed-list sizes.
- [ ] **ENG-20** `TikTokCreativeCenterAdapter` — best-effort, explicitly non-critical.
      Note: **not started.** Internal JSON endpoints, not a sanctioned API (R5). Isolate it; let it fail loudly and harmlessly.
- [x] **ENG-21** Persist raw payloads to JSONB alongside the parsed aggregate.
      Note: full series stored per signal (92 points on a 3-month daily window). Repository upserts with `ON CONFLICT DO NOTHING`.
- [x] **ENG-22** Celery beat schedule for periodic collection.
      Note: daily at 06:00 UTC. Schedule and task registration live in `celery_app.py` as the composition root, not scattered per context. **Seeds are hardcoded** in `tasks.py` until Niche Ranking feeds them back (M7) — fine for one operator, revisit when the seed list stops being hand-picked.
- [~] **TST-02** `TrendSource` contract suite, run against all three adapters. Cassettes for each.
      Note: suite exists and runs against every registered adapter — adding one is a single entry in `ADAPTERS`. Currently covers Google Trends + a fake; Etsy joins with ENG-18, TikTok with ENG-20. **Uses hand-written stubs, not VCR cassettes** — a stub shaped like the real DataFrame was enough to pin the `isPartial` and batching behaviour. Revisit if adapter bugs start slipping through.

### Ops ritual

- [ ] **OPS-01** Everbee or eRank subscription + a documented manual CSV-export → import routine.
      Note: no public API (R7). Manual by design. Decide whether it's worth the money after one month.

### Read model

- [x] **ENG-23** Niche Leaderboard view (server-rendered).
      Note: FastAPI + Jinja2 at `/niches` (settles **DEC-01** in practice — server-rendered, no build step, no second runtime). Shows score, confidence, status and the score's three components, with a banner counting single-source shortlists.
      **Open issue it exposed:** the board sorts by score, so a Google-only niche scored 88 sits *above* a fully-corroborated one at 80 — the least-evidenced row is at the top. That follows from the deliberate choice that confidence marks a thinner claim rather than a lower score. It is mostly a transient artifact of running one source: once ENG-18 lands nearly everything is HIGH and the ordering stops lying. **Revisit after ENG-18** — if it still misleads, discount the score by confidence rather than re-sorting, since re-sorting would bury genuine momentum spikes.
- [x] **ENG-23b** Cross-context bridge: `TrendSignal` → `NicheSignals`, plus niche persistence and the `RankNiches` use case.
      Note: not in the original plan; needed to connect the two contexts. Trend Discovery now has a **published facade** (`trend_discovery/public.py`) — a sibling of the layers, acting as the context's composition root, returning plain DTOs only. That is the single permitted cross-context edge, listed by name in the import-linter `ignore_imports`, so a second edge fails the build.
      **The contract earned its keep twice here.** The first draft reached into `trend_discovery.infrastructure.repository` — a genuine design flaw, caught by CI rather than review. The second was a cross-context test placed inside one context's `tests/`; it moved to the shared `tests/` root, where a test driving both contexts belongs.

**M2 exit:** leaderboard populated from ≥2 live sources on a schedule.
**Progress:** collection half done and proven end to end against live Google Trends into real Postgres. Remaining: ENG-16 (ranking domain), ENG-23 (leaderboard), ENG-20 (TikTok). ENG-18 waits on M0 credentials — so **the ≥2-live-sources exit criterion cannot be met until then**; Google Trends alone is momentum with no demand or competition signal to rank against.

---

## M3 — Manual loop validation *(run in parallel with M2)*

**Exit criterion:** 5 listings live, made entirely by hand, with real data on what the work actually involves.

This is not busywork and it is not optional. Automating a loop you have never run once produces a system that automates the wrong steps.

- [ ] **BIZ-10** Pick one niche by hand from early M2 output (or by judgment if M2 isn't ready).
      Note: this deliberately pre-empts CONTEXT.md §10's "first niche" question — pick one to *learn*, not to commit.
- [ ] **BIZ-11** Generate ~10 designs manually in whichever image tool. Time it. Record cost per usable image.
      Note: feeds BIZ-07 with real numbers instead of assumptions.
- [ ] **BIZ-12** Run all 10 through the CMP-04 IP checklist by hand. Record how long it takes and what it catches.
      Note: tells you whether this can ever be partly automated.
- [ ] **BIZ-13** Package files to Etsy's constraints — ≤5 files, ≤20MB each, filename ≤70 chars. Record what breaks.
      Note: this is where the R2 packaging gap becomes concrete.
- [ ] **BIZ-14** Write listing copy by hand: title, 13 tags, description, AI disclosure. Record what a good one looks like.
      Note: becomes the template and the eval set for ENG-26.
- [ ] **BIZ-15** Publish 5 listings manually. Note every field the API will need to fill.
      Note:
- [ ] **BIZ-16** Write up: where did the time actually go? Which step deserves automation first?
      Note: **this document reorders M4-M5 if it contradicts assumptions.** Expect it to.

**M3 exit:** 5 live listings + the BIZ-16 writeup.

---

## M4 — Generation & curation (the compliance boundary)

**Exit criterion:** an approved asset exists in the DB, created through the UI, and no code path can bypass the gate.

### Decisions first

- [ ] **DEC-02** Choose the image model. Criteria: **commercial license (hard gate)**, cost/image, print resolution, style control, API reliability.
      Note: `FLUX.1 [dev]` is **disqualified — non-commercial license** (R3). `[schnell]` is Apache 2.0; `[pro]` is commercial via BFL API. Verify Midjourney and Gemini terms the same way before deciding.

### Domain & generation

- [ ] **ENG-24** `content_generation` domain: `GeneratedAsset`, `AssetVariant`, `ProcessingJob`. Ports: `ImageGenerator`, `BackgroundRemover`, `Upscaler`. **Plus asset packaging to Etsy's file constraints** (R2 gap).
      Note: JPEG over PNG at 300 DPI — PNG runs 3-5× larger and blows the 20MB cap.
- [ ] **ENG-25** `creative_direction` domain: `StyleGuide`, `PromptTemplate`, `VariationSet`.
      Note: keep prompt templates in the DB, not in code. You'll tune them constantly.
- [ ] **ENG-26** Listing copy generation — title, 13 tags (≤20 chars each), description, via an LLM port. Eval against the BIZ-14 hand-written examples.
      Note: R2 gap. This is the traffic mechanism; without it, published listings are invisible.
- [ ] **ENG-27** Chosen `ImageGenerator` adapter + `rembg` for background removal (local, free).
      Note:
- [ ] **ENG-28** Cost tracking on every generation call from day one — emits `CostEvent`.
      Note: wire before volume, not after. Retrofitting this means a blind month.

### Curation

- [x] **ENG-29** `curation` domain: `ReviewDecision`, `ApprovalDecision`. Events: `AssetApproved`, `AssetRejected`.
      Note: `AssetApproved` can only be produced here, and only with a complete `IpScreening`. Decisions are final — re-approving or flipping a rejection raises, since that would strand events already emitted downstream. Rejection records a typed reason so Creative Direction can tell trademark risk from "off brief" and never re-roll an IP rejection into the same prompt set.
      Still to do for this context: persistence, application service, and the review queue UI (ENG-30).
- [ ] **ENG-30** Review Queue UI — **keyboard-first**, one asset per screen, J/K/A/R, no mouse required.
      Note: R6 — review speed is the throughput ceiling for the whole business. Treat this as the flagship surface.
- [~] **CMP-05** IP screening as a **blocking, explicit step** in the review flow — reviewer must actively confirm the CMP-04 checklist. No default-yes, no bulk-approve.
      Note: **enforced structurally in the domain.** The CMP-04 checklist is the `IpCheck` enum, and `IpScreening` refuses construction unless every member is cleared and a screener is named — so there is no representable state of "approved, screening partly done". `ReviewDecision.approve()` takes the screening as a **required positional argument**; an optional one with a permissive default is exactly how this check quietly stops happening the day someone adds a bulk-approve button.
      Remaining: the UI must surface the checks individually rather than pre-ticking them, and persistence must store who screened. Domain half is done and cannot be bypassed.
- [ ] **CMP-06** Enforce the approval gate at the **application-service** level: `DraftListing` requires a prior `AssetApproved` for that asset.
      Note: CONTEXT.md §2. Not a UI convention.
- [ ] **TST-03** Test that no path reaches `DraftListing` without `AssetApproved` — including queue-triggered and admin paths.
      Note: the test that protects the business. Run `compliance-guardian` against this milestone before merge.
- [ ] **TST-04** `ImageGenerator` contract suite.
      Note:

**M4 exit:** CMP-06 + TST-03 green, and `compliance-guardian` returns PASS.

---

## M5 — Listing authoring & publish

**Exit criterion:** a listing published to the real shop, by the pipeline, from an approved asset.

- [ ] **ENG-31** `listing_authoring` domain: `ListingDraft`, `PricingRule`, **`AIDisclosure` as a required VO**, plus title/tags/description from ENG-26.
      Note: constructing a publishable draft without disclosure must be structurally impossible — a type error, not a validation error.
- [ ] **ENG-32** `fulfillment` domain: `Listing`, `FulfillmentChannel` port, `ListingPublished` / `ListingPublishFailed`.
      Note:
- [ ] **ENG-33** `EtsyDigitalDownloadAdapter`.
      Note:
- [ ] **ENG-34** **Publish idempotency** — an idempotency key per draft; a retried or redelivered task must not create a second listing.
      Note: R2 gap. $0.20 per duplicate, non-refundable, and Celery redelivery is normal operation not an edge case.
- [ ] **ENG-35** Publish as **draft** first, with a manual "go live" action for the first N listings.
      Note: keeps a human between the pipeline and the public shop until it has earned trust. Remove the training wheel deliberately, not by forgetting.
- [ ] **ENG-36** Live Listings read model.
      Note:
- [ ] **CMP-07** `compliance-guardian` review of the entire publish path.
      Note: mandatory gate before this milestone closes.
- [ ] **TST-05** `FulfillmentChannel` contract suite (proves Phase 2 POD will slot in).
      Note:
- [ ] **OPS-02** Listing expiry handling — Etsy listings expire after 4 months. Decide renew vs let-die.
      Note: auto-renew re-charges $0.20. For a non-selling listing that's pure burn.

**M5 exit:** one pipeline-published live listing.

---

## M6 — Budgeting & production hardening

**Exit criterion:** the pipeline runs unattended for a week without cost surprises or silent failures.

- [ ] **ENG-37** `budgeting` domain: `SpendLedger`, `BudgetLimit`, `CostEvent`. Events: `SpendRecorded`, `BudgetCapReached`, `PipelinePaused`.
      Note: test the threshold at *exactly* the cap, not just over it.
- [ ] **ENG-38** Enforce the cap — `BudgetCapReached` pauses Trend Discovery and Content Generation.
      Note: verify every paid call path actually honors the pause. An unmetered paid call is the real failure mode.
- [ ] **ENG-39** Budget dashboard with daily/monthly burn.
      Note:
- [ ] **ENG-40** Cost-per-winning-listing calculation, using real M5 numbers.
      Note: run `economics-analyst` once there's a month of data.
- [ ] **DEC-03** Set real budget caps from BIZ-07 + BIZ-09.
      Note: closes CONTEXT.md §10's open question.
- [ ] **OPS-03** Deployment target + deploy process.
      Note: cheapest thing that runs one web + one worker + Postgres + Redis. A single small VPS is fine. Don't over-buy.
- [ ] **OPS-04** Error alerting to somewhere you actually read.
      Note: a silently dead scheduled job is the classic solo-project failure.
- [ ] **OPS-05** Postgres backups, restore **tested** at least once.
      Note: an untested backup is not a backup.
- [ ] **OPS-06** Secrets management in prod. Etsy refresh-token rotation handled.
      Note:
- [ ] **OPS-07** Structured logging with a correlation ID traced across the pipeline.
      Note:
- [ ] **OPS-08** Runbook: what to do when a source breaks, publish fails, or the budget cap trips.
      Note:

**M6 exit:** one week unattended, no cost surprise, no silent failure.

---

## M7 — Analytics & the feedback loop

**Exit criterion:** ranking weights adjust from real sales data.

Deliberately last. It needs traffic to learn from, and a new shop has none for weeks (PRD §7).

- [ ] **ENG-41** `analytics` domain: `ListingPerformance`, `RecordPerformanceSnapshot`, `PerformanceSnapshotRecorded`, `WinnerDetected`.
      Note:
- [ ] **ENG-42** `EtsyStatsAdapter` — views, favorites, orders.
      Note:
- [ ] **ENG-43** Scheduled snapshots.
      Note:
- [ ] **ENG-44** Define `WinnerDetected` thresholds from actual data.
      Note: don't guess this before ENG-43 has collected a month.
- [ ] **ENG-45** Feed the boost back into Niche Ranking.
      Note: the loop that makes the system improve instead of guessing forever. Keep it explainable — log why a weight moved.
- [ ] **ENG-46** Performance dashboard.
      Note:

**M7 exit:** one ranking weight demonstrably moved by real sales.

---

## M8 — Expansion *(only after M7 proves the loop)*

Nothing here starts until the core loop has produced revenue. Every item is deferred on purpose.

- [ ] **ENG-47** `PrintfulPodAdapter` / `PrintifyPodAdapter` behind `FulfillmentChannel` — no upstream changes.
      Note: the hexagonal payoff. If this requires touching any upstream context, the port was wrong.
- [ ] **CMP-08** Production-partner disclosure for POD listings.
      Note: non-negotiable once physical ships.
- [ ] **ENG-48** `AmazonSignalAdapter` (Keepa or Jungle Scout).
      Note: paid. Run `economics-analyst` first.
- [ ] **ENG-49** `EbaySignalAdapter`.
      Note: lowest-value signal. May never be worth it — mark `[-]` if so.
- [ ] **ENG-50** Multi-model A/B testing for image generation.
      Note:
- [ ] **ENG-51** ML-based niche ranking — **only if the weighted formula has demonstrably failed.**
      Note: CONTEXT.md §4.2. "Would be interesting" is not a reason.

---

# Part IV — Decision register

Open questions from CONTEXT.md §10 plus ones surfaced in review. Each needs a decision **by** a milestone.

| ID | Decision | Needed by | Recommendation | Status |
|---|---|---|---|---|
| **DEC-01** | Frontend for `dashboard/` | M4 | **FastAPI + Jinja2.** Settled in practice by ENG-23: the leaderboard is a server-rendered table with no build step and no second runtime. Add HTMX only when a page actually needs partial updates. Revisit only if the review queue needs drag-and-drop or live-updating budget bars. | `[x]` |
| **DEC-02** | Image generation model | M4 | Commercial license is a **hard gate** — `FLUX.1 [dev]` is out (R3). Shortlist `FLUX.1 [pro]` (BFL API) and `[schnell]`; verify Midjourney/Gemini terms before comparing on cost or quality. | `[ ]` |
| **DEC-03** | Budget cap numbers | M6 | Derive from BIZ-07. Do not pick a round number. | `[ ]` |
| **DEC-04** | First niche | M3 | Pick by hand to *learn*; let the M2 pipeline pick the one you *commit* to. | `[ ]` |
| **DEC-05** | Seller entity: individual vs business | M0 | Depends on jurisdiction + tax. Decide before BIZ-03 — changing it later is painful. | `[ ]` |
| **DEC-06** | Keep or drop Everbee/eRank after month 1 | M6 | Manual CSV ritual (R7). Keep only if it demonstrably changed a ranking decision. | `[ ]` |

---

# Part V — Risk register

| ID | Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|---|
| **RSK-01** | IP/trademark strike → shop suspension | **Fatal** | Medium | CMP-04 checklist, CMP-05 blocking review step, no brand/character/lyric designs ever |
| **RSK-02** | AI-disclosure violation → mass listing removal | **Fatal** | Low if CMP-06 holds | Structural enforcement in the aggregate, not validation |
| **RSK-03** | Etsy account correlated with scraping → ban | **Fatal** | Low | CONTEXT.md §5 — never scrape Etsy or Amazon. Non-negotiable. |
| **RSK-04** | Cash burn on generation before first sale | High | **High** | Budgeting from day one (M6), caps from real numbers, M3 manual validation first |
| **RSK-05** | Zero traffic for weeks → false failure signal | High | **High** | PRD §7. Judge on *first dollar*, not replacement income. SEO copy (ENG-26) is the lever. |
| **RSK-06** | pytrends / TikTok CC adapter breaks | Medium | **High** | ENG-17 graceful degradation. Never critical-path. |
| **RSK-07** | Review queue too slow → throughput ceiling | High | Medium | ENG-30 keyboard-first. Measure assets/minute as a real metric. |
| **RSK-08** | Image model license violation | High | Medium | DEC-02 treats license as a hard gate |
| **RSK-09** | Duplicate listings from retries | Low ($) | Medium | ENG-34 idempotency |
| **RSK-10** | Solo-operator burnout / abandonment | **Fatal** | Medium | Ship the M3 manual loop early for a morale win. Boring tech. Small milestones. |
| **RSK-11** | Etsy changes API or policy mid-build | Medium | Medium | Adapters isolate it. Re-read policy quarterly — put it in OPS-08. |
| **RSK-12** | Etsy API approval stalls or is refused | High | **Medium** | Manual review, no SLA, reports up to ~3 weeks (R4). Mitigation is **M3**: the manual loop needs no API, so the wait produces listings and real cost data instead of idle time. Nudge the help form after a week. If refused, the shop still works by hand and only the automation is blocked. |

---

# Part VI — Working agreements

- **`compliance-guardian` runs before any merge touching `curation`, `listing_authoring`, or `fulfillment`.** Not optional, not "when I remember."
- **`economics-analyst` runs before any change adding a paid API or raising generation volume.**
- **`domain-architect` designs a context's domain before its application or infrastructure code exists.**
- **ENG-07's import-linter contract is the enforcement mechanism for the dependency rule.** If it's disabled to unblock something, that's a bug to fix, not a lint to silence.
- **Update this file in the same commit as the work it tracks.** A roadmap updated retroactively is fiction.
- **A `[x]` with a caveat keeps its `Note:`.** "Done but needs migrations" is more useful than a clean checkbox that lies.

---

## Sources consulted for this review

- [Countries Eligible for Etsy Payments](https://help.etsy.com/hc/en-us/articles/115015710408-Countries-Eligible-for-Etsy-Payments)
- [Etsy Open API v3 — Rate Limits](https://developers.etsy.com/documentation/essentials/rate-limits/)
- [Etsy Open API v3 — Documentation](https://developers.etsy.com/documentation/)
- [Etsy AI Disclosure Policy 2026](https://ngini.com/en-us/blog/etsy-ai-disclosure-policy-2026-explained)
- [Etsy Creativity Standards — POD sellers guide](https://iscompliant.app/Blog/etsy-creativity-standards-pod-sellers-guide)
- [FLUX.1-dev license](https://huggingface.co/black-forest-labs/FLUX.1-dev/blob/main/LICENSE.md)
- [FLUX commercial usage and licensing](https://deepwiki.com/black-forest-labs/flux/5-commercial-usage-and-licensing)
- [How to Manage Your Digital Listings — Etsy Help](https://help.etsy.com/hc/en-us/articles/115015628347-How-to-Manage-Your-Digital-Listings)
- [Etsy copyright infringement breakdown](https://printify.com/blog/etsy-copyright-infringement/)
