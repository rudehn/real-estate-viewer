"""Load a CAMA export into parcel, parcel_detail, dwelling, parcel_feature,
parcel_value, neighborhood and tax_district, all in one transaction.

Runs in the background population loop. Parsing happens in worker threads
(bulk.in_thread_chunks) so the API keeps serving while a 2 GB export loads.
"""
from __future__ import annotations

import asyncio
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from county import cama
from county.coords import state_plane_to_wgs84
from county.neighborhood_codes import neighborhood_display_name
from county.tax_districts import district_info, jurisdiction_name
from db.county_models import (
    Dwelling,
    Neighborhood,
    ParcelDetail,
    ParcelFeature,
    ParcelValue,
    TaxDistrict,
)
from db.models import Parcel, ParcelClass
from ingest.bulk import in_thread_chunks, replace_rows, upsert
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


ATTACHED_GARAGE_CODES = {"13", "23"}
# 1919 means "built before 1920" (4,096 dwellings vs ~500 for neighboring
# years); 1900 is similarly inflated. Shown as approximate in the UI.
PLACEHOLDER_YEARS = {1900, 1919}
_ADDN_CODE_FIELDS = ("lower", "first", "second", "third")


def sketch_lines(addn_rows: list[dict]) -> list[dict]:
    return [
        {
            "line": row["lline"],
            "codes": [row[f] for f in _ADDN_CODE_FIELDS if row[f]],
            "area": row["area"],
            "vector": row["vect"],
        }
        for row in sorted(addn_rows, key=lambda r: r["lline"])
    ]


def _addn_by_card(zip_path: Path) -> dict[tuple[str, int], list[dict]]:
    """ADDN lines grouped per dwelling card, keeping only the fields we use."""
    grouped: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for row in _checked_rows(zip_path, "ADDN"):
        grouped[(row["parid"], row["card"])].append(
            {k: row[k] for k in ("lline", "area", "vect", *_ADDN_CODE_FIELDS)}
        )
    return grouped


def _dwelling_row(row: dict, addn: list[dict], ctx: CamaContext) -> dict:
    label = ctx.decodes.label
    garage = sum(
        line["area"] or 0
        for line in addn
        if ATTACHED_GARAGE_CODES & {line[f] for f in _ADDN_CODE_FIELDS}
    )
    return {
        "parcel_id": row["parid"],
        "card": row["card"],
        "living_sqft": row["sfla"],
        "first_floor_sqft": row["flr1area"],
        "finished_basement_sqft": row["finbsmtarea"] or None,
        "beds": row["rmbed"],
        "full_baths": row["fixbath"],
        "half_baths": row["fixhalf"],
        "stories": row["stories"],
        "style_code": row["style"],
        "style": label("DWELDAT", "STYLE", row["style"]),
        "year_built": row["yrblt"] or None,
        "year_built_is_placeholder": row["yrblt"] in PLACEHOLDER_YEARS,
        "grade": row["grade"],
        "grade_label": ctx.decodes.grade(row["grade"]),
        "condition": label("DWELDAT", "CDU", row["cdu"]),
        "exterior": label("DWELDAT", "EXTWALL", row["extwall"]),
        "basement": label("DWELDAT", "BSMT", row["bsmt"]),
        "heating": ctx.decodes.heat(row["heat"]),
        "fuel": label("DWELDAT", "FUEL", row["fuel"]),
        "has_central_air": row["heat"] == "4",
        "fireplaces": (row["wbfp_o"] or 0) + (row["wbfp_s"] or 0) + (row["wbfp_pf"] or 0),
        "attached_garage_sqft": garage,
        "basement_garage_cars": row["bsmtcar"] or 0,
        "sketch": json.dumps(sketch_lines(addn)) if addn else None,
        "snapshot_date": ctx.snapshot,
    }


async def load_dwellings(conn: AsyncConnection, ctx: CamaContext) -> int:
    addn = await asyncio.to_thread(_addn_by_card, ctx.zip_path)
    await conn.execute(sa.delete(Dwelling.__table__))
    written = 0
    rows = (
        _dwelling_row(r, addn.get((r["parid"], r["card"]), []), ctx)
        for r in _checked_rows(ctx.zip_path, "DWELL")
    )
    async for chunk in in_thread_chunks(rows):
        await conn.execute(sa.insert(Dwelling.__table__), chunk)
        written += len(chunk)
    return written


def _feature_row(row: dict, ctx: CamaContext) -> dict:
    return {
        "parcel_id": row["parid"],
        "card": row["card"],
        "line": row["lline"],
        "code": row["code"],
        "description": ctx.decodes.outbuilding(row["code"]),
        "year_built": row["yrblt"] or None,
        "area_sqft": row["area"],
        "width_ft": row["meas1"],
        "length_ft": row["meas2"],
        "condition": ctx.decodes.label("OBY", "COND", row["cond"]),
        "snapshot_date": ctx.snapshot,
    }


async def load_features(conn: AsyncConnection, ctx: CamaContext) -> int:
    await conn.execute(sa.delete(ParcelFeature.__table__))
    written = 0
    rows = (_feature_row(r, ctx) for r in _checked_rows(ctx.zip_path, "OBY") if r["code"])
    async for chunk in in_thread_chunks(rows):
        await conn.execute(sa.insert(ParcelFeature.__table__), chunk)
        written += len(chunk)
    return written


_VALUE_METHODS = {"1": "cost", "3": "override", "4": "income", "5": "cost (income suppressed)"}


def value_method(revcode: str | None) -> str | None:
    return _VALUE_METHODS.get(revcode) if revcode else None


def appeal_year(revreas: str | None) -> int | None:
    """Board of Revision appeals are coded B + 2-digit year (B96, B20)."""
    if not revreas or len(revreas) != 3 or revreas[0] != "B" or not revreas[1:].isdigit():
        return None
    yy = int(revreas[1:])
    return 2000 + yy if yy <= 40 else 1900 + yy


def _values_2026(zip_path: Path) -> dict[str, dict]:
    """2026 reappraisal values. Three parcels have two rows (split class): sum them."""
    out: dict[str, dict] = {}
    for row in _checked_rows(zip_path, "ASMT"):
        entry = out.setdefault(row["parid"], {"land": 0, "building": 0, "reascd": row["reascd"]})
        entry["land"] += row["aprland"] or 0
        entry["building"] += row["aprbldg"] or 0
    return out


def _value_row(row: dict, v2026: dict | None, ctx: CamaContext) -> dict:
    total_2025 = row["aprtot"]
    total_2026 = (v2026["land"] + v2026["building"]) if v2026 else None
    change = None
    if total_2025 and total_2026 is not None:
        change = round((total_2026 - total_2025) / total_2025 * 100, 3)
    return {
        "parcel_id": row["parid"],
        "land_2025": row["aprland"],
        "building_2025": row["aprbldg"],
        "total_2025": total_2025,
        "land_2026": v2026["land"] if v2026 else None,
        "building_2026": v2026["building"] if v2026 else None,
        "total_2026": total_2026,
        "change_pct": change,
        "value_method": value_method(row["revcode"]),
        "appeal_year": appeal_year(row["revreas"]),
        "tif": row["revreas"] == "TIF",
        "abated": row["revreas"] == "ABA",
        "reappraisal_reason": ctx.decodes.label("ASMT", "REASCD", v2026["reascd"])
        if v2026 else None,
        "snapshot_date": ctx.snapshot,
    }


async def load_values(conn: AsyncConnection, ctx: CamaContext) -> int:
    v2026 = await asyncio.to_thread(_values_2026, ctx.zip_path)
    await conn.execute(sa.delete(ParcelValue.__table__))
    written = 0
    rows = (
        _value_row(r, v2026.get(r["parid"]), ctx)
        for r in _checked_rows(ctx.zip_path, "APRVAL")
    )
    async for chunk in in_thread_chunks(rows):
        await conn.execute(sa.insert(ParcelValue.__table__), chunk)
        written += len(chunk)
    return written


async def load_neighborhoods_from_cama(conn: AsyncConnection, ctx: CamaContext) -> int:
    names = await asyncio.to_thread(cama.neighborhood_names, ctx.zip_path)
    table = Neighborhood.__table__
    rows = [
        {"code": code, "name": name, "display_name": neighborhood_display_name(name)}
        for code, name in names.items()
    ]
    for i in range(0, len(rows), 1000):
        stmt = upsert(conn)(table).values(rows[i : i + 1000])
        await conn.execute(stmt.on_conflict_do_nothing(index_elements=["code"]))
    parcel = Parcel.__table__
    pairs = await conn.execute(
        sa.select(parcel.c.neighborhood, parcel.c.tax_district, sa.func.count())
        .where(parcel.c.neighborhood.isnot(None), parcel.c.is_active.is_(True))
        .group_by(parcel.c.neighborhood, parcel.c.tax_district)
    )
    tallies: dict[str, Counter] = {}
    for code, district, n in pairs:
        tallies.setdefault(code, Counter())[district] += n
    for code, counter in tallies.items():
        await conn.execute(
            sa.update(table).where(table.c.code == code)
            .values(tax_district=counter.most_common(1)[0][0])
        )
    return len(rows)


async def load_tax_districts(conn: AsyncConnection) -> int:
    parcel = Parcel.__table__
    codes = (await conn.execute(
        sa.select(parcel.c.tax_district).where(parcel.c.tax_district.isnot(None)).distinct()
    )).scalars().all()
    rows = []
    for code in codes:
        name, school = district_info(code)
        rows.append({"code": code, "name": name, "jurisdiction": jurisdiction_name(code),
                     "school_district": school})
    return await replace_rows(conn, TaxDistrict.__table__, rows)


async def ingest_cama(zip_path: Path, engine: AsyncEngine | None = None) -> dict[str, int]:
    if engine is None:
        from db.engine import engine as default_engine

        engine = default_engine
    ctx = await asyncio.to_thread(load_context, Path(zip_path))
    counts: dict[str, int] = {}
    async with engine.begin() as conn:
        counts["parcel"] = await load_parcels(conn, ctx)
        counts["parcel_detail"] = await load_parcel_details(conn, ctx)
        counts["dwelling"] = await load_dwellings(conn, ctx)
        counts["parcel_feature"] = await load_features(conn, ctx)
        counts["parcel_value"] = await load_values(conn, ctx)
        counts["neighborhood"] = await load_neighborhoods_from_cama(conn, ctx)
        counts["tax_district"] = await load_tax_districts(conn)
    logger.info("CAMA %s ingested: %s", ctx.snapshot, counts)
    return counts
