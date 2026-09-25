"""Load the daily tax roll into parcel_tax (current tax year, one row per parcel)."""
from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from county.owners import classify_owner_name, mailing_state
from county.taxroll import TaxRollReader, snapshot_date
from county.text import normalize_search
from db.county_models import ParcelTax
from ingest.bulk import in_thread_chunks
from logging_config import get_logger

logger = get_logger(__name__)


def classify_occupancy(
    *,
    owner_occupied: bool,
    homestead: bool,
    owner_name: str | None,
    mailing_address1: str | None,
    situs: str | None,
) -> tuple[str, str]:
    if owner_occupied:
        return "owner_occupied", "Receives the owner-occupancy tax credit"
    if homestead:
        return "owner_occupied", "Has a homestead exemption"
    kind = classify_owner_name(owner_name)
    if kind:
        return kind, f"Owner name indicates a {kind}"
    mailing = normalize_search(mailing_address1)
    if mailing and mailing == normalize_search(situs):
        return "unknown", "Mails to the property but has no owner-occupancy credit yet"
    return "absentee_individual", "Individual owner with a mailing address elsewhere"


def _tax_row(row: dict, snapshot) -> dict:
    category, reason = classify_occupancy(
        owner_occupied=row["owner_occupied"],
        homestead=row["homestead"],
        owner_name=row["owner_name"],
        mailing_address1=row["mailing_address1"],
        situs=row["location"],
    )
    state = mailing_state(row["mailing_address3"]) or mailing_state(row["mailing_address2"])
    address = ", ".join(
        a for a in (row["mailing_address1"], row["mailing_address2"], row["mailing_address3"]) if a
    )
    return {
        "parcel_id": row["parcel_id"],
        "tax_year": row["tax_year"],
        "snapshot_date": snapshot,
        "annual_bill": row["annual_bill"],
        "gross_rate": row["gross_rate"],
        "effective_rate": row["effective_rate"],
        "market_value": row["market_value"],
        "owner_occupied": row["owner_occupied"],
        "homestead": row["homestead"],
        "rental_registered": row["rental_registered"],
        "foreclosure_date": row["foreclosure_date"],
        "cauv": row["cauv"],
        "abated": row["abated"],
        "net_delinquent": row["net_delinquent"],
        "balance_due": row["balance_due"],
        "census_tract": row["census_tract"],
        "zip": row["zip"],
        "city": row["city"],
        "owner_name": row["owner_name"],
        "owner_name2": row["owner_name2"],
        "mailing_name": row["mailing_name"],
        "mailing_address": address or None,
        "mailing_state": state,
        "out_of_state": state is not None and state != "OH",
        "occupancy": category,
        "occupancy_reason": reason,
    }


_COPY_TRACT = sa.text(
    """
    UPDATE parcel SET census_tract = (
        SELECT t.census_tract FROM parcel_tax t WHERE t.parcel_id = parcel.parcel_id
    )
    WHERE EXISTS (
        SELECT 1 FROM parcel_tax t WHERE t.parcel_id = parcel.parcel_id
          AND t.census_tract IS NOT NULL
    )
    """
)


async def ingest_taxroll(zip_path: Path, engine: AsyncEngine | None = None) -> int:
    if engine is None:
        from db.engine import engine as default_engine

        engine = default_engine
    snapshot = snapshot_date(zip_path)
    reader = TaxRollReader()

    def rows():
        seen = set()
        for row in reader.rows(Path(zip_path)):
            # Parcel ids are unique in practice; guard so one duplicate cannot
            # abort the whole load on the primary key.
            if row["parcel_id"] not in seen:
                seen.add(row["parcel_id"])
                yield _tax_row(row, snapshot)
        reader.check()

    table = ParcelTax.__table__
    written = 0
    async with engine.begin() as conn:
        await conn.execute(sa.delete(table))
        async for chunk in in_thread_chunks(rows()):
            await conn.execute(sa.insert(table), chunk)
            written += len(chunk)
        await conn.execute(_COPY_TRACT)
    logger.info("Tax roll %s ingested: %d parcels", snapshot, written)
    return written
