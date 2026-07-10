"""Automated scrape-and-populate pipeline.

Runs the full data-population sequence so the database fills itself after the
app is deployed - no manual CLI steps required:

  1. Download yearly sales CSVs from the county site (all years, current year
     always refreshed) to DATA_DIR.
  2. Ingest those CSVs into the DB.
  3. Download and ingest any new weekly sales ZIPs.
  4. Geocode parcels that are missing coordinates (for the map view).

Every step is idempotent: already-ingested files are skipped (DataFile dedup)
and already-geocoded parcels are skipped, so re-runs are cheap and safe. The
backend runs this once on startup and then on a repeating interval (see
`run_population_loop`), guarded by the AUTO_INGEST env var.
"""

import asyncio
import os

from db.ingestors import ingest_data_files, ingest_weekly_data
from services.data_retrieval import DATA_DIR, retrieve_yearly_data
from services.geocoding import CENSUS_BATCH_LIMIT, geocode_parcels
from logging_config import get_logger

logger = get_logger(__name__)

# Safety cap so a runaway geocode backlog can't loop forever in one pass.
_MAX_GEOCODE_BATCHES = 25


def _env_flag(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).lower() in ("1", "true", "yes", "on")


async def populate_once() -> None:
    """Run one full download -> ingest -> geocode pass."""
    logger.info("Population run starting (DATA_DIR=%s)...", DATA_DIR)

    # 1 + 2. Yearly history. retrieve_yearly_data is blocking (httpx.get +
    # zip extraction), so run it off the event loop.
    logger.info("Downloading yearly sales data...")
    await asyncio.to_thread(retrieve_yearly_data)
    logger.info("Ingesting yearly sales data...")
    await ingest_data_files(DATA_DIR)

    # 3. Recent weekly sales.
    logger.info("Ingesting new weekly sales data...")
    await ingest_weekly_data()

    # 4. Geocoding (optional).
    if _env_flag("GEOCODE", True):
        logger.info("Geocoding parcels missing coordinates...")
        for i in range(_MAX_GEOCODE_BATCHES):
            processed = await geocode_parcels(batch_size=CENSUS_BATCH_LIMIT)
            if not processed:
                break
        else:
            logger.info("Hit geocode batch cap (%d); more remain for next run.",
                        _MAX_GEOCODE_BATCHES)

    logger.info("Population run complete.")


async def run_population_loop() -> None:
    """Populate on startup, then repeat every INGEST_INTERVAL_HOURS.

    Designed to run as a background task. Individual run failures are logged and
    retried on the next interval rather than crashing the server.
    """
    interval = float(os.getenv("INGEST_INTERVAL_HOURS", "24")) * 3600
    while True:
        try:
            await populate_once()
        except asyncio.CancelledError:
            logger.info("Population loop cancelled.")
            raise
        except Exception:
            logger.exception("Population run failed; will retry next interval.")
        await asyncio.sleep(interval)
