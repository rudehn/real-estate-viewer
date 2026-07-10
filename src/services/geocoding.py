import asyncio
import csv
import io
import httpx
from sqlmodel import select, col
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker
from db.engine import engine
from db.models import Parcel
from logging_config import get_logger

logger = get_logger(__name__)

# Sentinel value stored in latitude to mark a parcel as permanently un-geocodable,
# so we don't waste API calls retrying it on every run.
_FAILED_SENTINEL = 0.0

CENSUS_BATCH_URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
# The batch endpoint accepts up to 10,000 rows per request.
CENSUS_BATCH_LIMIT = 10_000


async def geocode_parcels(batch_size: int = CENSUS_BATCH_LIMIT) -> int:
    """
    Geocode parcels with missing coordinates using the US Census batch API.

    Sends up to `batch_size` addresses in a single HTTP request instead of
    one request per parcel.  Parcels that the API cannot match are marked with
    latitude=0 so they are skipped on future runs.

    Returns the number of parcels processed in this batch (0 when none remain),
    so callers can loop until the backlog is cleared.
    """
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        statement = (
            select(Parcel)
            .where(Parcel.latitude == None)
            .limit(batch_size)
        )
        result = await session.exec(statement)
        parcels = result.all()

        if not parcels:
            logger.info("All parcels are already geocoded.")
            return 0

        logger.info("Geocoding batch of %d parcels via Census batch API...", len(parcels))

        # Build the CSV payload expected by the Census batch endpoint:
        # Unique ID, Street address, City, State, ZIP
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        for parcel in parcels:
            writer.writerow([parcel.parcel_id, parcel.parcel_location, "Dayton", "OH", ""])
        csv_bytes = csv_buffer.getvalue().encode()

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(
                    CENSUS_BATCH_URL,
                    data={"benchmark": "Public_AR_Current"},
                    files={"addressFile": ("addresses.csv", csv_bytes, "text/csv")},
                )
                response.raise_for_status()
            except Exception as e:
                logger.error("Census batch request failed: %s", e)
                return 0

        # Parse the response CSV.
        # Columns: ID, Input Address, Match, Match type, Matched address, Coords (lon,lat), Tiger ID, Side
        coords_by_id: dict[str, tuple[float, float]] = {}
        reader = csv.reader(io.StringIO(response.text))
        for row in reader:
            if len(row) < 6:
                continue
            parcel_id, _, match, _, _, coords_str = row[0], row[1], row[2], row[3], row[4], row[5]
            if match.strip().lower() != "match" or not coords_str.strip():
                continue
            try:
                lon_str, lat_str = coords_str.split(",")
                coords_by_id[parcel_id.strip()] = (float(lat_str), float(lon_str))
            except ValueError:
                continue

        matched = 0
        for parcel in parcels:
            if parcel.parcel_id in coords_by_id:
                parcel.latitude, parcel.longitude = coords_by_id[parcel.parcel_id]
                matched += 1
            else:
                # Mark as permanently failed so this parcel is skipped next run.
                parcel.latitude = _FAILED_SENTINEL
            session.add(parcel)

        await session.commit()
        logger.info(
            "Batch complete: %d matched, %d not found (marked as failed).",
            matched, len(parcels) - matched,
        )
        return len(parcels)