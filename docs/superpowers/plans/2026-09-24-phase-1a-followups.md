# Phase 1A follow-ups

Items found while executing and reviewing Phase 1A (data platform and /v2 API) that were deliberately not fixed on the `redesign` branch.
Plan 1B (frontend) and later phases should pick them up.

## Carry into plan 1B

- Cold aggregate endpoints (`/v2/market/summary`, `/v2/market/trends`, `/v2/neighborhoods`) take 2-4 s once per `data_version`.
  The population loop runs in the API process, so warming these caches at the end of `rebuild_derived` is a small follow-up.
- Unfiltered `/v2/sales?market_only=true` takes about 510 ms warm; storing an `is_market_sale` flag on `transaction` would remove the per-row criteria.
- The derived rebuild peaks at about 590 MB (fully fetched 260k-row summary join and map-binary query); streaming those queries in partitions would lower it.
- `services/analytics/*` import `api.filters`, `api.errors` and `api.cache`, while `api/__init__.py` imports every router: importing a service module before `main` hits a circular import.
  Move the filter model, error helpers and cache below `api` when 1B reshapes the API boundary.
- `rebuild_derived` bumps `data_version` on every run, so clients re-download the map binary daily; compare a content hash before bumping.
- Owner pages: holdings key on the tax-roll owner spelling and the activity profile on the sales-history spelling, so a name can resolve on one side only.
- The legacy unversioned routes in `src/main.py` still use `market_sale_criteria()` without the nominal-price rule; plan 1B deletes them with the old UI.
- `distress_min` is accepted and reported as honored, but distress scores are all 0 until phase 3; hide that filter in the UI until then.
- Occupancy `"unknown"` means either "no tax-roll row" or "mails to the property without the owner-occupancy credit"; label it "unverified" in the UI and show `occupancy_reason` on the profile.

## Test and maintenance gaps

- `tests/test_maintenance.py` fixtures are hard-wired to SQLite, so the pre-existing transaction repairs never run on Postgres in CI.
- Coverage gaps noted by task reviews: the absentee single-class filter path, `top_owners` ordering by parcels and acres, the `/v2/sales` count test across all filters, mixed-NULL price-per-square-foot buckets, an API-level nominal-price case above the $1,000 floor, and a same-day-sales tie-break in the parcel timeline.
- The search columns get the Postgres "C" collation only through `create_all` on new tables; a database that already has these tables from an earlier build of this branch would need a one-off index rebuild.

## Accepted behaviors worth knowing

- `latest_sale_date` (the "last N months" anchor) counts multi-parcel deals as data recency; per-parcel last sales exclude them.
- Tax-roll rows with a duplicated parcel id are dropped silently; `mailing_state` never falls back to the first mailing line.
- An owner name ending in the token `TR` is classified as a trust.
