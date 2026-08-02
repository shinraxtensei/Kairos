# Kairos — Project Context

*This file exists so any Claude session (or any future collaborator) can pick up this project cold. Read this first.*

## What this is

Kairos is a trend-discovery-to-Etsy-listing automation business. It watches for rising niches across multiple platforms, generates AI-assisted designs, routes them through a human curation step, and publishes them as Etsy listings — digital downloads first, with physical print-on-demand (Printful/Printify) designed in as a Phase 2 addition, not a rewrite.

Name: **Kairos** (Greek god of the opportune moment) — the whole business is a timing game: catching a niche as it rises, not after it's saturated.

## Business context

- Goal: build a real income stream, starting from zero, worldwide (not geography-locked)
- Etsy in 2026 still allows AI-assisted design but requires disclosure ("Designed by [seller]", not "Made by") and enforces an "original design" requirement — bulk near-identical AI listings get suspended. **Human curation is a compliance requirement here, not just a nice-to-have.**
- Unit economics matter more than pipeline sophistication — only ~1-5% of listings typically drive most revenue, so cost-per-winning-design (not cost-per-image) is the number that determines whether this is profitable. Model this in a spreadsheet before scaling any part of the pipeline.

## Architecture

- **One Python modular monolith** (FastAPI), not microservices. Solo dev, rent-pressure timeline — every network-service boundary is operational tax with no payoff at this scale.
- **DDD / hexagonal (ports & adapters)** within that monolith — each bounded context is a package with its own domain model, application services, and explicit ports for anything that talks outside (a data source, an image model, a marketplace).
- **Celery or RQ + Redis** for background jobs (replaces the original RabbitMQ plan — one broker, no separate deploy).
- **PostgreSQL only** (JSONB for raw/flexible data — no MongoDB).
- Repo layout: **one monorepo**, split into `backend/` (FastAPI + bounded-context packages) and `dashboard/` (frontend — framework TBD, reconsider whether Next.js is even needed yet vs. server-rendered pages). Split into separate repos only when there's a concrete reason (a second contributor, independent deploy needs) — not preemptively.

## Bounded contexts (see Miro board for full event storming)

Trend Discovery → Niche Ranking → Creative Direction → Content Generation → **Curation (human-in-the-loop)** → Listing Authoring → Fulfillment → Budgeting (cost guardrails) → Analytics (feeds back into Niche Ranking)

Full event-storming diagram (domain events, commands, aggregates, policies, external systems, read models per context): **https://miro.com/app/board/uXjVH2oHfmw=/**

## Data source strategy (important — avoid repeating past mistakes)

Raw scraping of Etsy and Amazon carries real risk: ToS violation, aggressive bot detection, and — critically — if a scraper IP/fingerprint gets correlated with the seller account, that risks the shop itself, not just the scraper. Use instead:

- **Etsy**: official Open API v3 + Everbee/eRank/Marmalead for market data
- **Amazon**: Keepa API or Jungle Scout API, not raw scraping
- **eBay**: official Browse/Marketplace Insights API where available, or a paid scraper-API vendor that absorbs the ToS risk
- **TikTok**: TikTok Creative Center (free, public, official — has a Top Products leaderboard by region/category/time window, exactly the signal needed, no scraping required)
- **Google Trends**: `pytrends` (unofficial but low-risk, no login/account to ban)

## Fulfillment — the hexagonal payoff

`FulfillmentChannel` is a port with one core method (`publish(listing) -> result`). `EtsyDigitalDownloadAdapter` ships first; `PrintfulPodAdapter` / `PrintifyPodAdapter` slot in later as new adapters without touching Trend Discovery, Niche Ranking, Creative Direction, or Content Generation. Same pattern applies to `TrendSource` (one adapter per platform) and `ImageGenerator` (one adapter per model — FLUX/Midjourney/Banana), so swapping providers is a config change.

## Build order (what to build first)

1. Domain models + ports for all contexts, no adapters yet
2. `EtsyTrendAdapter`, `GoogleTrendsAdapter`, `TikTokCreativeCenterAdapter` (lowest-risk, officially-sanctioned sources — skip Amazon/eBay scraping until the core pipeline proves out)
3. Niche Ranking with a simple weighted scoring function (not ML yet)
4. One `ImageGenerator` adapter + `EtsyDigitalDownloadAdapter`
5. The Curation dashboard — this is the compliance boundary, not optional scope
6. Budgeting wired in from day one

Physical POD, Amazon/eBay adapters, and multi-model A/B testing all come later as new adapters behind ports already built.
