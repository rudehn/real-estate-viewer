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

## Automated population

When `AUTO_INGEST=true`, the backend runs a background loop (`src/services/populate.py`) that:

1. Downloads yearly sales CSVs from the county site (current year always refreshed).
2. Ingests them.
3. Downloads and ingests any new weekly sales ZIPs.
4. Geocodes parcels missing coordinates via the US Census batch API.

Every step is idempotent (already-ingested files and already-geocoded parcels are skipped), so the deployed database fills itself with no manual steps.

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
