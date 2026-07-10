import glob
import os
import re
import asyncio
import httpx
import zipfile
from io import BytesIO
from datetime import datetime

from logging_config import get_logger

"""
This file handles retrieving data from the website
"""
logger = get_logger(__name__)
# Where downloaded CSVs are written. Overridable via DATA_DIR so the container
# can target a mounted volume (kept in sync with ingestion's DATA_DIR).
DATA_DIR = os.getenv("DATA_DIR", "data")

WEEKLY_INDEX_URL = "https://go.mcohio.org/applications/treasurer/search/fdpopup.cfm?dtype=WS"
WEEKLY_BASE_URL = "https://go.mcohio.org/applications/treasurer/search/data/Weekly"
_DOWNLOAD_CONCURRENCY = 5  # max simultaneous ZIP downloads


async def get_weekly_zip_urls() -> list[str]:
    """Scrapes the weekly sales index page and returns all ZIP download URLs."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(WEEKLY_INDEX_URL)
        response.raise_for_status()
    filenames = list(dict.fromkeys(re.findall(r"SALES_\d{8}_TO_\d{8}\.zip", response.text)))
    logger.info("Found %d weekly ZIP files on index page.", len(filenames))
    return [f"{WEEKLY_BASE_URL}/{fn}" for fn in filenames]


async def download_zip(
    client: httpx.AsyncClient, url: str, semaphore: asyncio.Semaphore
) -> tuple[str, bytes] | None:
    """Download a single ZIP, returning (url, raw_bytes) or None on failure."""
    async with semaphore:
        try:
            response = await client.get(url)
            response.raise_for_status()
            logger.info("Downloaded %s (%d KB)", url.split("/")[-1], len(response.content) // 1024)
            return url, response.content
        except Exception as e:
            logger.warning("Failed to download %s: %s", url, e)
            return None


async def download_weekly_zips(urls: list[str]) -> list[tuple[str, bytes]]:
    """Download all ZIPs concurrently (up to _DOWNLOAD_CONCURRENCY at once)."""
    semaphore = asyncio.Semaphore(_DOWNLOAD_CONCURRENCY)
    async with httpx.AsyncClient(timeout=60.0) as client:
        results = await asyncio.gather(*[download_zip(client, url, semaphore) for url in urls])
    return [r for r in results if r is not None]

def retrieve_yearly_data(force: bool = False):
    """
    Downloads yearly sales CSVs from the county website.
    Skips years where files are already present on disk unless force=True.
    The current calendar year is always re-fetched to pick up new sales.
    """
    yearly_data = f"{DATA_DIR}/yearly/"
    base_url = "https://go.mcohio.org/applications/treasurer/search/data/Yearly"
    current_year = datetime.now().year
    year = current_year
    min_year = 2001 # This is the earliest year of data on the website
    while year >= min_year:
        zip_name = f"SALES_{year}.zip"
        check_year = year
        year -= 1
        # Always re-fetch the current year (partial data); skip past years if already on disk
        is_current_year = check_year == current_year
        existing = glob.glob(f"{yearly_data}**/SALES_{check_year}*.csv", recursive=True)
        if existing and not force and not is_current_year:
            logger.info("Skipping %s (already on disk)", zip_name)
            continue
        full_url = f"{base_url}/{zip_name}"
        logger.info("Fetching %s", full_url)
        response = httpx.get(full_url)
        if response.status_code >= 400:
            logger.info("Skipping %s (HTTP %s)", full_url, response.status_code)
            continue
        myzip = zipfile.ZipFile(BytesIO(response.content))
        myzip.extractall(path=yearly_data)

