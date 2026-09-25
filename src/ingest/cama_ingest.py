"""Load a CAMA export into parcel, parcel_detail, dwelling, parcel_feature,
parcel_value and neighborhood, all in one transaction.

Runs in the background population loop. Parsing happens in worker threads
(bulk.in_thread_chunks) so the API keeps serving while a 2 GB export loads.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from county import cama
from county.coords import state_plane_to_wgs84
from db.county_models import ParcelDetail
from db.models import Parcel, ParcelClass
from ingest.bulk import in_thread_chunks, upsert
from logging_config import get_logger

logger = get_logger(__name__)

# ON CONFLICT upserts are single multi-row statements, so size them to stay
# under the 32,766 bind-parameter limit (12 columns x 2,000 rows).
_UPSERT_CHUNK = 2000


@dataclass
class LandTotals:
    acres: float = 0.0
    sqft: int = 0
    frontage: float | None = None
    depth: float | None = None


@dataclass
class LegalInfo:
    latitude: float | None
    longitude: float | None
    tax_district: str | None
    zip: str | None


@dataclass
class CamaContext:
    zip_path: Path
    snapshot: date
    decodes: cama.Decodes
    land: dict[str, LandTotals]
    legdat: dict[str, LegalInfo]


def _checked_rows(zip_path: Path, table: str):
    """Yield a table's rows, then fail if too many were unparseable."""
    reader, rows = cama.read_table(zip_path, table)
    yield from rows
    reader.check()


def load_context(zip_path: Path) -> CamaContext:
    land: dict[str, LandTotals] = {}
    for row in _checked_rows(zip_path, "LAND"):
        totals = land.setdefault(row["parid"], LandTotals())
        totals.acres += row["acres"] or 0.0
        totals.sqft += row["sf"] or 0
        if row["fronact"]:
            totals.frontage = max(totals.frontage or 0.0, row["fronact"])
        if row["depth"]:
            totals.depth = max(totals.depth or 0.0, row["depth"])
    legdat: dict[str, LegalInfo] = {}
    for row in _checked_rows(zip_path, "LEGDAT"):
        coords = state_plane_to_wgs84(row["xcoord"], row["ycoord"])
        legdat[row["parid"]] = LegalInfo(
            latitude=coords[0] if coords else None,
            longitude=coords[1] if coords else None,
            tax_district=row["taxdist"],
            zip=row["zip1"],
        )
    return CamaContext(
        zip_path=zip_path,
        snapshot=cama.snapshot_date(zip_path),
        decodes=cama.load_decodes(zip_path),
        land=land,
        legdat=legdat,
    )


def compose_address(house_number, direction, street, suffix, unit) -> str:
    parts = [str(house_number) if house_number else None, direction, street, suffix, unit]
    return " ".join(p for p in parts if p)


def _unit(row: dict) -> str | None:
    return " ".join(p for p in (row["unitdesc"], row["unitno"]) if p) or None


def _parcel_row(row: dict, ctx: CamaContext) -> dict:
    land = ctx.land.get(row["parid"], LandTotals())
    legal = ctx.legdat.get(row["parid"])
    acres = land.acres or row["acres"] or 0.0
    return {
        "parcel_id": row["parid"],
        "parcel_location": compose_address(
            row["adrno"], row["adrdir"], row["adrstr"], row["adrsuf"], _unit(row)
        ),
        "parcel_class": ParcelClass.__members__.get((row["class"] or "")[:1], ParcelClass.R),
        "acres": round(acres, 4),
        "latitude": legal.latitude if legal else None,
        "longitude": legal.longitude if legal else None,
        "coord_source": "county" if legal and legal.latitude is not None else None,
        "neighborhood": row["nbhd"],
        "tax_district": (legal.tax_district if legal else None) or row["parid"][:3],
        "land_use_code": row["luc"],
        "zip": row["zip1"] or (legal.zip if legal else None),
        "is_active": True,
    }


async def load_parcels(conn: AsyncConnection, ctx: CamaContext) -> int:
    table = Parcel.__table__
    # Everything starts inactive; parcels present in this export flip back.
    await conn.execute(sa.update(table).values(is_active=False))
    written = 0
    async for chunk in in_thread_chunks(
        (_parcel_row(r, ctx) for r in _checked_rows(ctx.zip_path, "PARDAT")), size=_UPSERT_CHUNK
    ):
        stmt = upsert(conn)(table).values(chunk)
        excluded = stmt.excluded
        stmt = stmt.on_conflict_do_update(
            index_elements=["parcel_id"],
            set_={
                # Keep the sales-history location string, class and acres of
                # parcels we already know; refresh the county-owned columns.
                "neighborhood": excluded.neighborhood,
                "tax_district": excluded.tax_district,
                "land_use_code": excluded.land_use_code,
                "zip": excluded.zip,
                "is_active": excluded.is_active,
                "latitude": sa.func.coalesce(excluded.latitude, table.c.latitude),
                "longitude": sa.func.coalesce(excluded.longitude, table.c.longitude),
                "coord_source": sa.func.coalesce(excluded.coord_source, table.c.coord_source),
            },
        )
        await conn.execute(stmt)
        written += len(chunk)
    # Parcels still located only by the Census geocoder (0.0 marks a failure).
    await conn.execute(
        sa.update(table)
        .where(table.c.coord_source.is_(None), table.c.latitude.isnot(None),
               table.c.latitude != 0)
        .values(coord_source="census")
    )
    return written


def _detail_row(row: dict, ctx: CamaContext) -> dict:
    land = ctx.land.get(row["parid"], LandTotals())
    return {
        "parcel_id": row["parid"],
        "land_use_code": row["luc"],
        "land_use": ctx.decodes.label("ASMT", "LUC", row["luc"]),
        "living_units": row["livunit"],
        "house_number": row["adrno"] or None,
        "street_direction": row["adrdir"],
        "street_name": row["adrstr"],
        "street_suffix": row["adrsuf"],
        "unit": _unit(row),
        "city": row["cityname"],
        "zip": row["zip1"],
        "lot_sqft": land.sqft or None,
        "lot_acres": round(land.acres, 4) if land.acres else row["acres"],
        "frontage_ft": land.frontage,
        "depth_ft": land.depth,
        "snapshot_date": ctx.snapshot,
    }


async def load_parcel_details(conn: AsyncConnection, ctx: CamaContext) -> int:
    await conn.execute(sa.delete(ParcelDetail.__table__))
    written = 0
    async for chunk in in_thread_chunks(
        _detail_row(r, ctx) for r in _checked_rows(ctx.zip_path, "PARDAT")
    ):
        await conn.execute(sa.insert(ParcelDetail.__table__), chunk)
        written += len(chunk)
    return written


async def ingest_cama(zip_path: Path, engine: AsyncEngine | None = None) -> dict[str, int]:
    if engine is None:
        from db.engine import engine as default_engine

        engine = default_engine
    ctx = await asyncio.to_thread(load_context, Path(zip_path))
    counts: dict[str, int] = {}
    async with engine.begin() as conn:
        counts["parcel"] = await load_parcels(conn, ctx)
        counts["parcel_detail"] = await load_parcel_details(conn, ctx)
    logger.info("CAMA %s ingested: %s", ctx.snapshot, counts)
    return counts
