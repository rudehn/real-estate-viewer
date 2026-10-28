# Real Estate Viewer

This project provides a UI to view and analyze real-estate transactions in part of Ohio (Montgomery County).
Public county data is scraped, processed, and served via an API.
A FastAPI backend scrapes and serves the sales/parcel data; a Next.js frontend renders maps, tables, and charts on top of it.

## Architecture

- **Backend** (`src/`): FastAPI + SQLModel, served by uvicorn on port 8000.
  Backed by Postgres in production (SQLite is used only for local dev and tests).
- **Frontend** (`frontend/`): Next.js app on port 3000.
  It talks to the backend same-origin under `/api`, which Next.js proxies to the backend (see `frontend/next.config.mjs`), so no backend host is baked into the build.
- **Deployment**: both are built into images published to GHCR and run on the home-server via the `real-estate-viewer` stack.
  See the home-server repo's `stacks/real-estate-viewer/`.

## Configuration (environment variables)

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | local `database.db` (SQLite) | SQLAlchemy async URL. Production sets `postgresql+asyncpg://...`. |
| `DATA_DIR` | `data` | Where downloaded CSVs are written and ingested from. |
| `AUTO_INGEST` | `false` | When true, the backend self-populates the DB in the background on startup and on a schedule. |
| `INGEST_INTERVAL_HOURS` | `24` | How often the background population loop re-runs. |
| `GEOCODE` | `true` | Whether the population run geocodes parcels missing coordinates. |
| `COUNTY_INGEST` | `true` | Whether the population run also ingests CAMA, the tax roll and neighborhood names. |

The frontend reads its browser-visible keys from its own environment on each request (see `frontend/src/app/dashboard/layout.tsx`), so the published image needs no rebuild to change them.

| Variable | Default | Purpose |
|----------|---------|---------|
| `CARTO_API_KEY` | unset | Key for CARTO's dark basemap, free at <https://carto.com/basemaps/apikey>. Unset, dark mode shows inverted OpenStreetMap tiles instead. |
| `GOOGLE_MAPS_API_KEY` | unset | Enables the Street View image on parcel pages. Unset, the page links to Google Maps instead. |

## Automated population

When `AUTO_INGEST=true`, the backend runs a background loop (`src/services/populate.py`) that:

1. Downloads and ingests the yearly sales CSVs from the county site (current and previous year always refreshed).
2. Downloads and ingests any new weekly sales ZIPs.
3. Ingests the newest CAMA export (monthly): parcels, dwellings, features, values and county coordinates.
4. Ingests the newest neighborhood names (monthly).
5. Ingests the newest tax roll (weekly): bills, delinquency and occupancy.
6. Geocodes, via the US Census batch API, only the parcels the county does not locate.
7. Rebuilds the derived data: `parcel_summary`, `neighborhood_summary` and the map binary.

Every step is idempotent (files whose exact content was already ingested and already-geocoded parcels are skipped), so the deployed database fills itself with no manual steps.
A failing step is logged and the remaining steps still run.

The county publishes each sale several times: in weekly ZIPs shortly after it is recorded, then in every monthly re-export of the yearly file.
The yearly export is authoritative (corrected buyer names, validity codes, and the neighborhood and deed columns that weekly files lack), so yearly rows overwrite stored ones, while weekly rows only fill in sales newer than the last yearly export.
See the top of `src/db/ingestors.py` for the exact rules.

### Resource needs

The population loop runs inside the API process, so size the container for its peak.
A population run over the full county (the August 2026 CAMA export, the September 2026 tax roll and the derived rebuild, on SQLite) peaked at about 600 MB resident memory.
The CAMA step peaks at about 420 MB and the derived rebuild at about 590 MB.
Give the backend at least 1 GB of memory.

## API

The frontend uses the versioned `/v2` API.
Its OpenAPI document is committed at `frontend/openapi.json`; regenerate it with `uv run python scripts/export_openapi.py` after changing the API.
`/analytics` and the other unversioned routes remain until the new frontend ships.

## Data sources

See [docs/data-sources/README.md](docs/data-sources/README.md) for the county files we ingest, their layouts and profiling findings.
`uv run python scripts/verify_real_data.py` runs every ingest step against a copy of `database.db` and the newest county files, then reports coverage and endpoint latency.

## Local development

```
uv sync
uv run uvicorn main:app --app-dir src --reload --host 0.0.0.0
cd frontend && npm install && npm run dev
```

The same work can also be driven manually via the CLI.

## CLI commands

Run with `uv run python src/cli.py <command>`.

| Command | Description |
|---------|-------------|
| `init` | Create database tables |
| `fetch` | Download fresh yearly CSV data from the web |
| `ingest [directory]` | Ingest CSV files from the data directory (default: `data`) |
| `ingest-weekly` | Fetch and ingest all new weekly sales ZIPs from the county website |
| `geocode` | Geocode all un-geocoded parcels using the Census batch API (10,000/request) |
| `geocode --loops 13` | Run 13 batches, enough to cover all ~120k missing parcels |
| `geocode --batch-size 5000` | Use a smaller batch size per request |

> **Note:** Parcels that the Census API cannot match are marked with `latitude=0` so they are skipped on future runs.

## Database revisions

```
alembic init -t async migrations
```

- Update `alembic.ini`: set `sqlalchemy.url`.
- Update `migrations/env.py`: import `db.models` and set `target_metadata = SQLModel.metadata`.

```
alembic revision --autogenerate -m "Add latitude and longitude to parcels"
alembic upgrade head
```
