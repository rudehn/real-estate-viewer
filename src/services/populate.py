"""Automated scrape-and-populate pipeline.

Runs the full data-population sequence so the database fills itself after the
app is deployed - no manual CLI steps required:

  1. Download yearly sales CSVs from the county site (all years, current and
     previous year always refreshed) to DATA_DIR.
  2. Ingest those CSVs into the DB.
  3. Download and ingest any new weekly sales ZIPs.
  4. Geocode parcels that are missing coordinates (for the map view).

Every step is idempotent: files whose exact content was already ingested are
skipped (DataFile name + content hash) and already-geocoded parcels are
skipped, so re-runs are cheap and safe. The
backend runs this once on startup and then on a repeating interval (see
`run_population_loop`), guarded by the AUTO_INGEST env var.
"""

import asyncio
import os
from pathlib import Path

from db.ingestors import ingest_data_files, ingest_weekly_data
from derived.summary import rebuild_derived
from ingest.cama_ingest import ingest_cama
from ingest.neighborhood_ingest import ingest_neighborhood_names
from ingest.taxroll_ingest import ingest_taxroll
from logging_config import get_logger
from services.county_sync import sync_dataset
from services.data_retrieval import DATA_DIR, retrieve_yearly_data
from services.geocoding import CENSUS_BATCH_LIMIT, geocode_parcels

logger = get_logger(__name__)

# Safety cap so a runaway geocode backlog can't loop forever in one pass.
_MAX_GEOCODE_BATCHES = 25


def _env_flag(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).lower() in ("1", "true", "yes", "on")


async def _run_step(name: str, step) -> None:
    """Run one pipeline step, logging (not raising) any failure.

    The steps are independent - weekly ingest does not need the yearly files,
    and geocoding works on whatever parcels exist - so one broken step (e.g. a
    county-site outage on the yearly download) must not starve the others.
    """
    try:
        await step()
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Population step '%s' failed; continuing.", name)


async def _yearly() -> None:
    # retrieve_yearly_data is blocking (httpx.get + zip extraction), so run it
    # off the event loop.
    logger.info("Downloading yearly sales data...")
    await asyncio.to_thread(retrieve_yearly_data)
    logger.info("Ingesting yearly sales data...")
    await ingest_data_files(DATA_DIR)


async def _weekly() -> None:
    logger.info("Ingesting new weekly sales data...")
    await ingest_weekly_data()


async def _geocode() -> None:
    logger.info("Geocoding parcels missing coordinates...")
    for _ in range(_MAX_GEOCODE_BATCHES):
        processed = await geocode_parcels(batch_size=CENSUS_BATCH_LIMIT)
        if not processed:
            break
    else:
        logger.info("Hit geocode batch cap (%d); more remain for next run.",
                    _MAX_GEOCODE_BATCHES)


COUNTY_DATA_DIR = Path(DATA_DIR) / "county"


async def _cama() -> None:
    await sync_dataset("cama", lambda path, engine: ingest_cama(path, engine=engine),
                       data_dir=COUNTY_DATA_DIR)


async def _neighborhood_names() -> None:
    await sync_dataset(
        "neighborhoods",
        lambda path, engine: ingest_neighborhood_names(path, engine=engine),
        data_dir=COUNTY_DATA_DIR,
    )


async def _taxroll() -> None:
    # Published daily; a weekly refresh is plenty for bills and occupancy.
    await sync_dataset("taxroll", lambda path, engine: ingest_taxroll(path, engine=engine),
                       data_dir=COUNTY_DATA_DIR, min_age_days=7)


async def _derived() -> None:
    await rebuild_derived()


async def populate_once() -> None:
    """Run one full download -> ingest -> geocode -> derive pass."""
    logger.info("Population run starting (DATA_DIR=%s)...", DATA_DIR)
    await _run_step("yearly", _yearly)
    await _run_step("weekly", _weekly)
    if _env_flag("COUNTY_INGEST", True):
        await _run_step("cama", _cama)
        await _run_step("neighborhood_names", _neighborhood_names)
        await _run_step("taxroll", _taxroll)
    # After CAMA, so the Census geocoder only handles parcels the county lacks.
    if _env_flag("GEOCODE", True):
        await _run_step("geocode", _geocode)
    await _run_step("derived", _derived)
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
