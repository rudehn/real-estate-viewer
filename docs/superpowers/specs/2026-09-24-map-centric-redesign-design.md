# Map-centric redesign: design spec

Date: 2026-09-24
Status: approved in conversation, pending written-spec review

## 1. Goal

Rewrite the frontend as a modern, sleek, fast, map-centric app, and extend the data platform with the county's other public datasets.
The app serves two audiences, investor-first: an approachable overview and search for anyone, with deep investor and distress tools one click away.
Desktop is the primary platform; mobile is designed deliberately but is secondary.
The visual direction is "map-centric, refined minimal": the map is the persistent canvas, and neutral floating panels carry the content.

### Success criteria

- Every current capability exists in the new UI, with the known correctness problems fixed (see section 11).
- Filtering the full county updates the map at 60fps with no server round trip.
- Any view, filter, and selection is a shareable URL.
- A property profile answers "what is this house, what is it worth, who owns it, and is it in trouble" on one screen.
- The four new feature areas ship: property intelligence, distress radar, investor vs owner-occupant, permits and renovation.
- Works at 1440px desktop and 390px phone, in light and dark themes, with no layout overflow.

### Non-goals

- User accounts, saved searches, alerts, or any write features.
- Counties other than Montgomery County, Ohio.
- Street View imagery beyond an outbound link (no paid map APIs).
- Historic building characteristics (the CAMA export is a single current snapshot).

## 2. Data inventory

The county publishes nine datasets; see `docs/data-sources/README.md` for URLs and the profiling reports.

| Dataset | Used for | Decision |
|---|---|---|
| Weekly/monthly/yearly sales | Sales, trends, flips | Already ingested; keep |
| CAMA (monthly zip, 35 tables) | Buildings, lots, features, permits, values, deed types, neighborhood names, coordinates | Ingest selected tables |
| Tax roll (daily) | Full parcel list, tax bill, occupancy, foreclosure dates, census tract | Ingest weekly, plus one snapshot per tax year 2019-2025 |
| Delinquent taxes (monthly) | Delinquency status and history | Ingest monthly, plus history backfill |
| Neighborhood codes (monthly) | Official names | Ingest monthly |
| District listings | Duplicates the tax roll | Skip |
| Tax refunds | 381 rows, low value | Skip |

Key facts that shape the design:

- Parcel IDs join directly to our `parcel.parcel_id` after trimming whitespace; CAMA and the tax roll cover 97-98% of our parcels, and the misses are retired parcel IDs.
- The tax roll and CAMA contain about 255k active parcels; our DB only has the 179k that have sold.
- 61% of our transactions have a NULL neighborhood; CAMA `PARDAT.nbhd` and the tax roll fill it.
- About 38k of our parcels lack usable coordinates; CAMA `LEGDAT` State Plane coordinates cover 249k parcels.
- CAMA values exist only for tax year 2025 and the 2026 reappraisal; longer value history comes from yearly tax roll snapshots.
- Permit records in Dayton, Kettering, and Oakwood are sparse compared to the suburbs, so permit views need a coverage indicator.

## 3. Phasing

One spec, implemented in four phases that each ship independently.

| Phase | Scope | Acceptance |
|---|---|---|
| 1. Foundation | Parcel universe from CAMA `PARDAT`; CAMA building, lot, and value ingest; current tax roll ingest (bill and occupancy); neighborhood names; coordinate and neighborhood backfills; `/v2` API with search and server-side paging; new frontend shell (map canvas, rail, search, filters, panels, design system); property profile; every existing capability migrated into the Explore, Market, Investors, Distress, and Sales modes; YoY fix | Parity checklist below passes; old UI and old endpoints deleted in the same change |
| 2. Market and investors | Tax roll history ingest (one snapshot per tax year), $/sq ft everywhere, choropleths, occupancy mix, LLC buyer trend, reappraisal map, tax burden by district | All listed views live with tests |
| 3. Distress radar | Delinquency ingest and backfill, special assessments, CAMA deed types, distress score, watchlist, heat map, trend | Score factors visible on every distressed parcel |
| 4. Permits | Permit ingest and categorization, coverage indicators, parcel permit timeline, renovation-aware flips, new-build and teardown tracker; the Permits rail item appears in this phase | All listed views live with tests |

The `cama` ingestion step grows with each phase: phase 1 loads `PARDAT`, `LAND`, `LEGDAT`, `DWELL`, `ADDN`, `OBY`, `APRVAL`, `ASMT`, and `NBHD`; phase 3 adds `SASMT`, `PROJECT`, and `SALES`; phase 4 adds `PERMIT`.

Phase 1 parity checklist (everything the current UI does, in its new home):

- Explore: KPIs with comparison deltas, median price and volume trends with month/quarter/year granularity, seasonal activity heatmap, data health.
- Map: individual sales colored by price, neighborhood choropleth by median price, sales count, and total volume.
- Market: neighborhood rankings, neighborhood price trends, top buyers and sellers, price timeline.
- Investors: top owners by properties, acres, and value; acquisition waves; net sellers; absentee owners; owner portfolio page with activity, map, holdings, and related entities.
- Distress: distressed sales (with nominal transfers excluded) and stale parcels.
- Sales: sortable, paginated sales table and flip detection.
- Property profile: sale history, price history chart, comps, map link.
- Owner search (now through the ⌘K palette), dark mode, PWA manifest and icons.

Work happens on the `redesign` branch.
Backend changes are additive and deploy first; the frontend merges when phase 1 reaches parity.

## 4. Layout and navigation

### 4.1 Persistent map canvas

The map mounts once in the root layout and never reloads when the route changes.
Changing views changes the panel content, the map's color layer, and the camera, with animated transitions.

```
┌──┬──────────────────────────────────────────────────────────────┐
│◉ │ [⌘K Search address, owner, parcel…]  [Date][Price][Type][+] │
│⌂ │ ┌───────────────┐                                  ┌───────┐ │
│▤ │ │ PANEL         │          MAP CANVAS              │Layer ▾│ │
│◎ │ │               │                                  └───────┘ │
│⚠ │ │               │                                  ┌───────┐ │
│⚒ │ │               │                                  │Legend │ │
│☰ │ └───────────────┘                                  └───────┘ │
└──┴──────────────────────────────────────────────────────────────┘
```

- Left icon rail: the modes, the data-freshness chip, and the theme toggle.
- Top: the search bar (opens the ⌘K palette) and the filter chip bar.
- Left floating panel: contextual content.
- Top right: the "Color by" layer control.
- Bottom right: the legend for the active layer.

### 4.2 Modes

| Mode | Route | Panel | Default map layer |
|---|---|---|---|
| Explore | `/` | County at a glance: KPIs for the filtered set, trend sparklines, top movers | Last sale price |
| Market | `/market` | Price, volume, and $/sq ft trends; neighborhood rankings; reappraisal change; tax burden by district | $/sq ft choropleth |
| Investors | `/investors` | Occupancy mix; top owners; LLC buyer share over time; acquisition waves; net sellers | Occupancy category |
| Distress | `/distress` | Watchlist; delinquency trend; factor breakdown | Distress score heat map |
| Permits | `/permits` | Activity trends; renovation-aware flips; new construction and teardowns | Permit activity |
| Sales | `/sales` | Full sales table (server-side paged, sortable, CSV export) | Recent sales |

### 4.3 Panel behavior

- The panel is **narrow** (420px) for context views and **wide** (about 60% of the viewport) for tables and chart-heavy views.
- The map stays visible and linked in both widths: hovering a table row highlights its parcel, and clicking a map dot opens it in the panel.
- Drill-down is a stack: county, then neighborhood (`/n/[code]`), then parcel (`/p/[parcelId]`), then owner (`/o/[owner]`).
- The panel has a back control and breadcrumbs, and every step is a real URL.

### 4.4 Property profile (`/p/[parcelId]`)

Sections, top to bottom:

1. Header: title-cased address, neighborhood, badges (owner-occupied, LLC-owned, absentee, delinquent, foreclosure filed, open permit), Street View link.
2. Key facts: beds, full/half baths, living sq ft, year built, stories, style, grade, condition, basement, A/C, garage, lot size, notable features (pool, outbuildings).
3. Value: last market sale and $/sq ft, $/sq ft vs neighborhood median, county market value 2025 and 2026 with % change, ratio of county value to last sale, appeal and TIF flags.
4. Floor plan: SVG footprint drawn from the CAMA sketch vectors, with living, garage, porch, and deck areas labeled.
5. Timeline: sales, permits, and delinquency events merged chronologically.
6. Taxes: annual bill and its components, effective rate vs the tax district median, special assessments, delinquency status.
7. Distress: score and the factors that fired (phase 3).
8. Owner: name, occupancy classification with its reasoning, mailing location, link to the owner portfolio.
9. Comps: matched comparable sales listed and highlighted on the map.

Sections whose data is missing say so explicitly ("No dwelling on record", "Permit records are limited in Dayton").

### 4.5 Filters

- Global filter chips: date range, price, property type, beds, sq ft, year built, occupancy, distress.
- Each chip opens a popover with presets (for dates: last 12 months, year to date, last 5 years, all) and exact number inputs next to any slider.
- The map filters instantly on the GPU; panel queries run after a 250ms debounce.
- Slider values commit on release, not on every drag tick.
- Active filters show as chips with a remove control and a total count.
- Any panel section that cannot honor a filter shows a "Not filtered by: price" note, driven by the API's `applied_filters` field.

### 4.6 Mobile

- Full-screen map with a bottom sheet (three snap points) in place of the side panel.
- A bottom tab bar replaces the rail.
- Filters open in a full-height sheet.
- Tables render as stacked cards below 640px.
- Touch targets are at least 44px; safe-area insets are respected; heights use `dvh`.

## 5. Visual design system

- **Surfaces:** floating panels, search, and controls are slightly translucent cards with backdrop blur, a 1px hairline border, a soft shadow, and 12px radius.
- **Basemap:** grayscale light and dark styles so data carries the color.
- **Palette:** neutral zinc grays plus one accent, the deep green from the existing app icon, tuned for contrast in both themes.
  The accent is reserved for interactive state (selection, active mode, primary actions) and never encodes data.
  All colors are OKLCH tokens in Tailwind v4; `themeColor` matches the accent.
- **Data colors:** a separate, colorblind-safe system validated in both themes.
  Sequential ramp for magnitudes (price, $/sq ft, year built).
  Diverging ramp around a neutral midpoint for changes (reappraisal %, YoY).
  Categorical set of at most six hues for occupancy and permit categories.
  Warm yellow-to-red ramp for distress.
  A metric uses the same colors in charts and on the map, and every map layer has a legend.
- **Typography:** Inter with tabular numerals everywhere; a monospace face for parcel IDs.
  KPI values large and semibold, labels small and muted, no all-caps labels.
- **Display casing:** county text arrives in ALL CAPS; addresses and names render with smart title case that preserves tokens such as LLC, LP, II, III, and directional abbreviations.
- **Formatting:** `$148K` and `$1.2M` in summaries, full dollars in detail rows, dates as `Mar 13, 2026`, missing values as "Not recorded" (never `0.00`).
- **Motion:** 150-200ms ease-out panel transitions, map fly-to on selection, number tweens on KPI changes; all disabled under `prefers-reduced-motion`.
- **States:** skeletons shaped like the final content; empty states that explain the cause and suggest an action; inline errors with retry.
- **Glossary:** (i) popovers for jargon such as arm's-length sale, grade, condition (CDU), certified delinquent, homestead, CAUV, TIF.
- **Components:** shadcn (base-ui) generated for Tailwind v4, lucide icons, `cmdk` palette, Recharts through shadcn chart wrappers with horizontal-only light gridlines, themed tooltips, and nice tick values.

## 6. Data platform

### 6.1 Ingestion steps

New steps in `services/populate.py`, each idempotent, independently failing, and recorded in `DataFile`.

| Step | Cadence | Source | Target tables |
|---|---|---|---|
| `cama` | Monthly, when a newer file is listed | `Cama_Files_*.zip` | `parcel` universe, `parcel_detail`, `dwelling`, `parcel_feature`, `permit`, `parcel_value`, `cama_sale`, `special_assessment`, `neighborhood` |
| `taxroll` | Weekly (latest daily file) | `TAXROLL_*.zip` | `parcel_tax` |
| `taxroll_history` | One-time, one file per tax year 2019-2025 | `TAXROLL_*.zip` | `parcel_tax_year` |
| `delinquency` | Monthly, plus one-time backfill | `Delq_*.zip` | `delinquency_snapshot` |
| `neighborhood_names` | Monthly | `neighborhood_codes_*.htm` | `neighborhood` |
| `derived` | After any successful step above | Local tables | `parcel_summary`, `neighborhood_summary`, map binary |

Tax district names are a static JSON file in the repo seeded from `docs/data-sources/lookups/tax_district_names.json` and completed by hand.

### 6.2 Tables

| Table | Grain | Key contents |
|---|---|---|
| `parcel` (extended) | Parcel | Adds `neighborhood`, `tax_district`, `land_use_code`, `zip`, `census_tract`, `is_active`, `coord_source` |
| `parcel_detail` | Parcel | Land use, living units, situs address parts, lot sq ft, frontage, depth, acres (from LAND), site codes |
| `dwelling` | Parcel, card | Living sq ft, beds, full/half baths, stories, style, year built (with a `year_built_is_placeholder` flag for 1900 and 1919), grade, condition, exterior, basement, finished basement sq ft, heat, fuel, A/C, fireplaces, attached garage sq ft, sketch vectors as JSON |
| `parcel_feature` | Parcel, item | Outbuildings and yard items (garage, shed, pool, pole building, mobile home) with size and year |
| `permit` | Permit | Permit number, date, raw type, normalized category, amount, status, description |
| `parcel_value` | Parcel | 2025 land/building/total market value, 2026 values, % change, value method, appeal year, TIF and abatement flags |
| `cama_sale` | Sale | Deed type, instrument number, multi-parcel group id, value at sale (2024-10 onward) |
| `special_assessment` | Parcel, category | Amounts per normalized category (delinquent utility, weeds/nuisance, TIF, lighting, other) |
| `neighborhood` | Code | Official name, display name, tax district |
| `tax_district` | Code | Jurisdiction name, school district |
| `parcel_tax` | Parcel | Annual bill and components, effective rate, owner-occupied flag, homestead type, rental registration, foreclosure date, CAUV, abatement, census tract |
| `parcel_tax_year` | Parcel, tax year | Market value, bill, owner-occupied flag |
| `delinquency_snapshot` | Parcel, snapshot date | Net delinquent amount, certified delinquent year, status code, foreclosure date |
| `parcel_summary` | Parcel | Denormalized row for the map, search, and filters (section 6.4) |
| `neighborhood_summary` | Neighborhood | Occupancy mix, housing stock, reappraisal change, parcel counts |

Homestead data is stored only as an exemption type code; applicant names, addresses, and notes are never stored.

### 6.3 Parcel universe and backfills

- `parcel` grows to all active parcels from the tax roll and CAMA `PARDAT`; parcels missing from both are marked `is_active = false`, not deleted.
- Coordinates come from CAMA `LEGDAT` State Plane (EPSG:3735, US feet), converted to WGS84 with `pyproj`.
  The Census geocoder remains as a fallback for parcels without county coordinates; `coord_source` records which was used.
- Neighborhood lives on `parcel`; transaction queries join to it instead of relying on `transaction.neighborhood`.
- Existing DB columns named `assessed_*` hold 100% market value and `taxable_*` hold the 35% value; the DB columns stay as they are, and the API exposes `market_value` and `assessed_value_35pct`.

### 6.4 Derived logic

**Occupancy category** (one per parcel):

1. Owner-occupied if the tax roll `OWNOCC = Y` or a homestead exemption exists.
2. Otherwise government if the owner name matches a government pattern (city, county, state, land bank, HUD, school district, and so on).
3. Otherwise company if the name matches an entity pattern (LLC, INC, CORP, LP, LTD, and so on).
4. Otherwise trust if the name matches a trust pattern.
5. Otherwise absentee individual.

An independent `out_of_state_owner` flag comes from the mailing address.
The panel shows the rule that produced each classification.

**Distress score:** additive points, with every contributing factor stored and displayed.

| Factor | Points |
|---|---|
| Foreclosure date within the last 24 months | 40 |
| Certified delinquent for 3+ years | 25 |
| Certified delinquent for 1-2 years | 15 |
| Net delinquent amount above 10% of market value | 15 |
| Weeds or nuisance special assessment | 10 |
| Delinquent utility special assessment | 10 |
| Sheriff deed in the last 24 months | 10 |

The score is capped at 100; the weights live in one module so they can be tuned.

**Permit categories:** a rules table maps the permit-number prefix and the free-text type to one of: new dwelling, addition, remodel, demolition, roof, HVAC, electrical, plumbing, pool, deck or fence, solar, commercial, other.
Each tax district gets a permit coverage ratio (permits per 100 parcels since 2015); districts below a threshold show "limited permit records".

**Renovation-aware flips:** a flip is a resale within 24 months with at least a 10% gain where the buy side is an arm's-length market sale.
Flips with a renovation-class permit between the two sales are labeled "renovation"; others are labeled "no permits on file".

**Comps:** valid market sales in the last 24 months, same neighborhood (widening to a 1-mile radius when fewer than 5), same style family, living sq ft within 20%, beds within 1, baths within 1, year built within 15 years, ranked by a similarity score.

**`parcel_summary` columns:** id, lat, lng, class, land use, neighborhood, tax district, last market sale date and price, $/sq ft of that sale, living sq ft, beds, baths, year built, 2026 market value, 2025-2026 value change %, occupancy category, out-of-state flag, distress score, distress factor bitmask, permit count in the last 5 years, last permit date, annual tax bill.

### 6.5 Robustness

- New tables are created by `create_all`; new columns on existing tables are added by idempotent startup repairs in `db/maintenance.py` (prod never runs alembic).
- All SQL is portable between Postgres and SQLite; date math goes through `db/sqlutil.py`.
- Parsers stream from zip files and handle cp1252 text, records wrapped across physical lines, overflow continuation lines, `###` numeric overflow, two-digit years (1964-2026 range), and the known layout PDF errors documented in `docs/data-sources/`.
- A parser counts and logs bad rows; a file with more than 1% bad rows is rejected and the step fails.
- Full-refresh tables load into a staging table and swap atomically in one transaction.
- The derived step bumps a `data_version` that keys all caches.

## 7. API

### 7.1 Structure

- `main.py` is split into routers: `parcels`, `sales`, `market`, `neighborhoods`, `owners`, `investors`, `distress`, `permits`, `search`, `map`, `meta`.
- Query logic lives in a `services/` layer; routers only validate input and shape output.
- New routes live under `/v2`; the old routes are deleted when the phase 1 frontend merges.

### 7.2 Filter contract

A single Pydantic model covers `date_from`, `date_to`, `price_min`, `price_max`, `classes`, `beds_min`, `sqft_min`, `sqft_max`, `year_built_min`, `year_built_max`, `occupancy`, `distress_min`, and `neighborhood`.
Every list and aggregate endpoint accepts it, and every response includes `applied_filters`: the filter names that endpoint honored.

### 7.3 Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /v2/map/parcels.bin` | Columnar binary of `parcel_summary` for deck.gl; gzip; ETag is the data version; long cache with revalidation |
| `GET /v2/map/neighborhoods` | Neighborhood boundaries (GeoJSON) with static summary stats |
| `GET /v2/search?q=` | Grouped results: addresses, owners, parcel IDs, neighborhoods; prefix match on normalized indexed columns; up to 8 per group |
| `GET /v2/parcels/{id}` | Full property profile |
| `GET /v2/parcels/{id}/timeline` | Sales, permits, and delinquency events |
| `GET /v2/parcels/{id}/comps` | Comparable sales with similarity scores |
| `GET /v2/sales` | Server-side paginated and sorted sales with filters |
| `GET /v2/sales.csv` | CSV export of the full filtered set, streamed |
| `GET /v2/market/summary` | KPIs; comparison windows anchored to the latest sale date in the data and labeled |
| `GET /v2/market/trends` | Median price, $/sq ft, and volume by month, quarter, or year |
| `GET /v2/neighborhoods`, `GET /v2/neighborhoods/{code}` | Filtered neighborhood stats; neighborhood report |
| `GET /v2/owners/top`, `GET /v2/owners/{name}` | Top owners; portfolio, activity, related entities |
| `GET /v2/investors/occupancy`, `GET /v2/investors/llc-trend` | Occupancy mix by area; LLC buyer share by year |
| `GET /v2/distress/watchlist`, `GET /v2/distress/trend` | Ranked distressed parcels with factors; delinquency history |
| `GET /v2/permits/trends`, `GET /v2/permits/flips`, `GET /v2/permits/new-construction` | Permit activity; renovation-aware flips; new builds and teardowns |
| `GET /v2/meta` | Data version, freshness per source, filter value ranges |

### 7.4 Map binary format

- A little-endian binary: a 4-byte header length, a JSON header (row count, data version, and for each column its name, type, byte offset, and any category labels), then the column buffers aligned to 4 bytes.
- Numeric columns are `Float32`, `Uint16`, or `Uint8`; categories are `Uint8` codes with labels in the header; parcel IDs are a newline-joined UTF-8 block.
- The binary is regenerated by the derived step and cached on disk and in memory.

### 7.5 Types, performance, errors

- TypeScript types are generated from the OpenAPI schema with `openapi-typescript`; CI fails if the generated file is stale.
- Indexes cover every filter and sort column.
- Aggregate endpoints use an in-process cache keyed by `data_version` and the normalized filter.
- Target p95 under 300ms for panel endpoints on prod Postgres.
- Errors use one JSON shape (`{"error": {"code", "message"}}`); unknown parcels and owners return 404; invalid filters return 422 with a readable message.

## 8. Frontend architecture

### 8.1 Stack

Next.js 15 (App Router), React 19, TypeScript, Tailwind v4, shadcn (base-ui), TanStack Query, TanStack Table and Virtual, `nuqs`, Zustand, MapLibre GL, deck.gl, PMTiles, Recharts, `cmdk`, lucide.
The existing Dockerfile, standalone output, multi-arch GHCR publishing, and `/api` proxy stay.

### 8.2 Routing

- `app/(map)/layout.tsx` owns the map canvas, rail, search, filter bar, and panel frame.
- Route pages render only panel content and declare their map scene with `useMapScene({ layer, highlight, camera })`.
- Routes: `/`, `/market`, `/investors`, `/distress`, `/permits`, `/sales`, `/p/[parcelId]`, `/n/[code]`, `/o/[owner]`.

### 8.3 State

- URL (`nuqs`): filters, layer, mode, selection.
- Server data (TanStack Query): query keys include `data_version`.
- Map interaction (Zustand): hover, highlighted parcel sets, camera requests.

### 8.4 Map engine (`lib/map/`)

- A Web Worker fetches and decodes `parcels.bin` into typed arrays and builds the id-to-index map.
- The parcel layer is a deck.gl `ScatterplotLayer` with `DataFilterExtension`; range and category filters are GPU uniforms, so changing a filter re-uploads nothing.
- Color attributes for each "Color by" layer are computed in the worker and transferred.
- The worker computes live counts and medians for the current filter.
- The distress layer is a deck.gl `HeatmapLayer` weighted by score.
- Neighborhood choropleths are a MapLibre fill layer driven by feature-state.
- Highlights (comps, portfolio, hovered row) are a small separate overlay layer.
- The basemap is a Protomaps PMTiles extract of the county region, pulled at Docker build time and served from our own origin, with grayscale light and dark styles.

### 8.5 Components

- `components/ui`: shadcn primitives.
- `components/shell`: rail, search bar, filter bar, panel frame, breadcrumbs, freshness chip, legend, layer control.
- `components/panel`: section, stat grid, KPI with sparkline, "not filtered" note, empty and error states.
- `components/charts`: themed wrappers for line, bar, area, and stacked charts.
- `components/parcel`: facts grid, floor plan, timeline, tax card, distress factors, comps list.
- `components/tables`: one virtualized data table used everywhere, with desktop rows and mobile cards.
- `components/search`: command palette.
- `lib/format`: currency, numbers, dates, smart title case, "Not recorded".
- `lib/glossary`: popover definitions.

### 8.6 Budgets

- App shell under 200KB gzipped JavaScript; map libraries load in parallel and never block the panel.
- Largest Contentful Paint under 2.5s on desktop.
- Filter interactions at 60fps on the map.
- Panel data p95 under 300ms.

### 8.7 Accessibility

- Full keyboard navigation for the rail, palette, filters, and tables, with visible focus rings.
- Panels are labeled regions; the palette follows the combobox pattern.
- Colorblind-safe palettes, and never color alone to convey meaning.
- Every map view has a list or table equivalent in the panel.

## 9. Error handling

- Ingestion steps fail independently and log with context.
- `/v2/meta` reports freshness per source; the freshness chip turns amber when sales are older than 14 days or CAMA is older than 45 days.
- Panel sections fail independently with an inline retry.
- If the map binary fails to load, the panel keeps working and the map shows a retry card.

## 10. Testing

- Backend (pytest):
  - Parser tests on small real fixture excerpts committed to the repo, covering each known quirk.
  - Unit tests for occupancy classification, distress score, permit categorization, comps matching, flip labeling, and the tax bill formula.
  - API tests for every `/v2` endpoint, including `applied_filters` and error shapes.
  - Suite runs against SQLite and Postgres.
- Frontend:
  - Vitest for format helpers, title casing, the binary decoder, and filter logic.
  - Playwright end-to-end at 1440px and 390px, light and dark: search to profile, filters update map count and panel, mode switching keeps the map mounted, sales table sort, page, and export, table hover highlights the map.
- Each phase ends with a screenshot review of every view at both sizes and themes, and visual defects are fixed before sign-off.
- A CI test workflow runs backend tests (SQLite and a Postgres service), frontend lint and typecheck, Vitest, the generated-types check, and Playwright.

## 11. Known issues this design fixes

- Price and acreage slider tracks, checkbox states, and focus rings are unstyled because the shadcn components target Tailwind v4 while the app runs v3.4.
- The app lays out at 784px on a 390px phone (fixed sidebar and non-wrapping nav).
- KPI "YoY" windows count back from today instead of from the latest data, producing false drops when data is stale.
- Flip and distressed-sale lists are dominated by nominal $1,000 transfers.
- The price timeline plots only the latest 5,000 sales but is labeled as the full range, with an axis padded a year past the data.
- Transaction sorting only sorts the 5,000 rows loaded in the browser.
- The filter sidebar appears on pages whose data ignores it.
- Neighborhood is missing on 61% of transactions, and 0 acres renders as "0.00 acres" in some places and as a dash placeholder in others.
- The parcels list page is orphaned from navigation.
- `leaflet.markercluster` is installed but unused, and 10,000 overlapping circles form dark blobs.
- Dark mode heatmap ramp is inverted and negative KPI badges are unreadable.
- Owner search in the sidebar refetches on every keystroke, and sliders refetch on every drag tick.
- The local `.venv` was copied from another project and its script shebangs point at a missing path; recreate it with `uv sync`.
