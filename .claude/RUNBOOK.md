# Kairos — Runbook

OPS-08. What to do when something breaks, written before it breaks, because the
version written during an incident is always worse.

Every scheduled task tags its logs with a `correlation_id`. Start any
investigation by finding it, then follow it — that is the whole point of having
one.

```bash
grep '"correlation_id":"collect-' logs | jq .
```

---

## The failure that produces no error

**A scheduled job silently stops running.** No exception, no alert from any
error tracker, nothing in the logs — because nothing ran. For a solo operator
this is the most likely serious failure and the hardest to notice.

Check first, always:

```bash
make logs
```

```sql
SELECT max(collected_at) FROM trend_signals;
SELECT max(scored_at)    FROM niches;
```

If the newest row is older than a day, beat is not running. Restart it
(`make beat`) and check why it died before assuming it was a blip.

---

## A trend source is failing

**Symptom:** `TrendSourceSyncFailed` in the logs, fewer sources than expected in
the run summary.

This is designed to be survivable — a failing source degrades the run, it does
not stop it (ENG-17). Do not treat one broken source as an outage.

| Source | Usual cause | Action |
|---|---|---|
| Google Trends | 429, or Google moved its endpoints | Wait. It rate-limits aggressively — three runs in an afternoon will trip it. If it persists over days, pytrends likely needs updating. |
| eBay | 401 | Token or credentials wrong. Check `KAIROS_EBAY_CLIENT_ID`/`_SECRET`. |
| Keepa | 429 "token limit" | Keepa's own token budget, not ours. It refills hourly. |
| Etsy | 401/403 | Refresh token expired — it dies after 90 days of disuse. Re-run `scripts/etsy_oauth.py`. |

**Every source failed** raises an alert. That is worth acting on; one source is
not.

---

## The pipeline has paused itself

**Symptom:** `BudgetCapReached` then `PipelinePaused`; `/budget` shows a red bar.

Working as designed. Check `/budget` for which cap bound and where the money
went by category.

- **Daily cap** — clears at midnight UTC on its own.
- **Monthly cap** — clears at month start.
- **Genuinely need more room:** raise `KAIROS_DAILY_BUDGET` / `KAIROS_MONTHLY_BUDGET`.

Before raising a cap, look at the category breakdown. A cap hit early in the
month usually means something is generating more than intended, not that the cap
is too low — and raising it turns a working guard into a larger bill.

Etsy listing and transaction fees never count toward a cap; if they appear to,
that is a bug.

---

## A publish failed

**Symptom:** `ListingPublishFailed`, listing stuck in `failed`.

Safe to retry. The idempotency guard means a retry cannot create a duplicate:
the draft id derives a stable key, `listings.draft_id` is unique, and an already
published draft is refused before the channel is touched (ENG-34).

```sql
SELECT draft_id, state, attempts, failure_reason FROM listings WHERE state = 'failed';
```

If `attempts` is climbing with the same reason, stop retrying and read the
reason — repeated identical failures are a wrong request, not bad luck.

**Never** work around it by publishing manually while a `pending`/`failed` row
exists. That creates a listing the system does not know about, and it will try
to publish again.

---

## A listing was removed by Etsy

**Treat this as serious, immediately.** Removals cluster: the same cause usually
affects everything published in that batch.

1. Read the notice — AI-disclosure, IP, or originality?
2. Find the asset's review record:
   ```sql
   SELECT * FROM review_decisions WHERE asset_id = '<id>';
   ```
   It records who approved it and which IP checks were confirmed.
3. **IP:** find every listing from the same style guide. If one design infringed,
   its siblings likely do too.
4. **Originality/templated:** the `VariationSet` rules exist to prevent this. If
   a removed batch passed them, the rules are too loose — tighten them before
   publishing anything else.
5. Strikes accumulate and a pattern means permanent suspension. One removal is a
   warning; two in a batch is a stop-everything.

---

## Database

```bash
make down && make up && make migrate
```

Restore is untested until OPS-05 is done. **Do not assume a backup works —
until it has been restored once, it is a hope, not a backup.**

---

## Rotating the Etsy refresh token

It grants publish rights and expires after 90 days of disuse.

```bash
cd backend && uv run python scripts/etsy_oauth.py
```

Replace `KAIROS_ETSY_REFRESH_TOKEN` in `.env` and restart both processes. Logging
redacts it, so it should never appear in output — if you ever see it in a log,
treat it as leaked and rotate immediately.

---

## Local development

| Problem | Fix |
|---|---|
| `no configuration file provided` | Use `make`, not raw `docker compose` — the compose file lives in `backend/` |
| `ModuleNotFoundError: kairos` | Use `make`, not bare `python` — deps are in a uv venv |
| `Address already in use` | `make stop`, or `make dev PORT=8001` |
| `/review` empty after `make test` | Expected. Tests use `kairos_test`, but `make seed` wipes and refills dev data |

---

## What is deliberately not automated

- **Approving an asset.** The compliance gate is permanent, not a training wheel.
- **Republishing a live listing.** `force` refuses; delete on the channel first.
- **Raising a budget cap.** Requires a human deciding the money is worth it.
