"""parcel_summary, neighborhood_summary and data_version.

Everything is rebuilt from scratch in one transaction after each population
run, so readers always see one consistent version.
"""
from __future__ import annotations

import asyncio
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from county.text import normalize_search, street_key
from db.county_models import (
    DataVersion,
    Dwelling,
    NeighborhoodSummary,
    OwnerIndex,
    ParcelSummary,
    ParcelTax,
    ParcelValue,
)
from db.criteria import market_sale, market_sale_criteria
from db.models import Parcel, Transaction
from ingest.bulk import insert_rows
from logging_config import get_logger

logger = get_logger(__name__)


def _last_market_sales():
    """Newest single-parcel market sale per parcel (parcel_id, sale_date, sale_price)."""
    t = Transaction.__table__
    deals = (
        sa.select(
            t.c.parcel_id, t.c.sale_date, t.c.sale_price, t.c.id,
            sa.func.count().over(
                partition_by=[t.c.sale_date, t.c.new_owner, t.c.sale_price]
            ).label("deal_size"),
        )
        .where(market_sale())
        .subquery()
    )
    ranked = (
        sa.select(
            deals.c.parcel_id, deals.c.sale_date, deals.c.sale_price,
            sa.func.row_number().over(
                partition_by=deals.c.parcel_id,
                order_by=[deals.c.sale_date.desc(), deals.c.id.desc()],
            ).label("rn"),
        )
        .where(deals.c.deal_size == 1)
        .subquery()
    )
    return sa.select(ranked.c.parcel_id, ranked.c.sale_date, ranked.c.sale_price).where(
        ranked.c.rn == 1
    ).subquery("last_sale")


def _dwelling_totals():
    d = Dwelling.__table__
    ranked = sa.select(
        d.c.parcel_id, d.c.living_sqft, d.c.beds, d.c.full_baths, d.c.half_baths,
        d.c.year_built, d.c.year_built_is_placeholder,
        sa.func.row_number().over(
            partition_by=d.c.parcel_id,
            order_by=[sa.func.coalesce(d.c.living_sqft, 0).desc(), d.c.card],
        ).label("rn"),
    ).subquery()
    primary = ranked.c.rn == 1
    return sa.select(
        ranked.c.parcel_id,
        sa.func.sum(ranked.c.living_sqft).label("living_sqft"),
        sa.func.sum(ranked.c.beds).label("beds"),
        (sa.func.sum(sa.func.coalesce(ranked.c.full_baths, 0))
         + 0.5 * sa.func.sum(sa.func.coalesce(ranked.c.half_baths, 0))).label("baths"),
        sa.func.max(sa.case((primary, ranked.c.year_built))).label("year_built"),
        sa.func.max(sa.case((primary, sa.cast(ranked.c.year_built_is_placeholder, sa.Integer))))
        .label("year_built_is_placeholder"),
    ).group_by(ranked.c.parcel_id).subquery("dw")


async def build_parcel_summary(conn: AsyncConnection) -> int:
    """Rows are normalized in a worker thread, chunk by chunk, by insert_rows."""
    p, v, tx = Parcel.__table__, ParcelValue.__table__, ParcelTax.__table__
    last, dw = _last_market_sales(), _dwelling_totals()
    ppsf = sa.case(
        (sa.and_(dw.c.living_sqft > 0, last.c.sale_price > 0),
         last.c.sale_price * 1.0 / dw.c.living_sqft),
    )
    query = (
        sa.select(
            p.c.parcel_id, p.c.latitude, p.c.longitude, p.c.parcel_class, p.c.land_use_code,
            p.c.neighborhood, p.c.tax_district, p.c.is_active,
            p.c.parcel_location.label("address"),
            tx.c.owner_name, tx.c.occupancy, tx.c.out_of_state, tx.c.annual_bill,
            last.c.sale_date, last.c.sale_price, ppsf.label("ppsf"),
            dw.c.living_sqft, dw.c.beds, dw.c.baths, dw.c.year_built,
            dw.c.year_built_is_placeholder,
            v.c.total_2026, v.c.change_pct,
        )
        .select_from(p)
        .outerjoin(tx, tx.c.parcel_id == p.c.parcel_id)
        .outerjoin(last, last.c.parcel_id == p.c.parcel_id)
        .outerjoin(dw, dw.c.parcel_id == p.c.parcel_id)
        .outerjoin(v, v.c.parcel_id == p.c.parcel_id)
    )
    rows = (await conn.execute(query)).mappings().all()

    def summary_rows():
        for r in rows:
            address = r["address"] or ""
            latitude = r["latitude"] if r["latitude"] else None  # 0.0 = failed geocode
            yield {
                "parcel_id": r["parcel_id"],
                "parcel_id_search": r["parcel_id"].replace(" ", "").upper(),
                "latitude": latitude,
                "longitude": r["longitude"] if latitude is not None else None,
                "parcel_class": r["parcel_class"].name if hasattr(r["parcel_class"], "name")
                else r["parcel_class"],
                "land_use_code": r["land_use_code"],
                "neighborhood": r["neighborhood"],
                "tax_district": r["tax_district"],
                "is_active": bool(r["is_active"]),
                "address": address or None,
                "address_search": normalize_search(address) or None,
                "street_search": street_key(normalize_search(address)) or None,
                "owner_name": r["owner_name"],
                "owner_search": normalize_search(r["owner_name"]) or None,
                "last_sale_date": r["sale_date"],
                "last_sale_price": r["sale_price"],
                "price_per_sqft": r["ppsf"],
                "living_sqft": r["living_sqft"],
                "beds": r["beds"],
                "baths": float(r["baths"]) if r["living_sqft"] is not None else None,
                "year_built": r["year_built"],
                "year_built_is_placeholder": bool(r["year_built_is_placeholder"]),
                "market_value": r["total_2026"],
                "value_change_pct": r["change_pct"],
                "occupancy": r["occupancy"] or "unknown",
                "out_of_state_owner": bool(r["out_of_state"]),
                "annual_tax": r["annual_bill"],
            }

    await conn.execute(sa.delete(ParcelSummary.__table__))
    return await insert_rows(conn, ParcelSummary.__table__, summary_rows())


async def build_owner_index(conn: AsyncConnection) -> int:
    """One row per distinct owner name: active parcel count, or 0 for past buyers only.

    The merge and normalization run in a worker thread (insert_rows pulls rows()).
    """
    s, t = ParcelSummary.__table__, Transaction.__table__
    current = (await conn.execute(
        sa.select(s.c.owner_name, sa.func.count().label("n"))
        .where(s.c.is_active.is_(True), s.c.owner_name.isnot(None))
        .group_by(s.c.owner_name)
    )).all()
    past_owners = (await conn.execute(sa.select(t.c.new_owner).distinct())).scalars().all()

    def rows():
        counts = {name: n for name, n in current}
        for name in past_owners:
            counts.setdefault(name, 0)
        for name, count in counts.items():
            search = normalize_search(name)
            if not search:
                continue
            yield {"name": name, "name_search": search, "parcel_count": count}

    await conn.execute(sa.delete(OwnerIndex.__table__))
    return await insert_rows(conn, OwnerIndex.__table__, rows())


async def latest_sale_date(conn: AsyncConnection) -> date | None:
    t = Transaction.__table__
    return (await conn.execute(
        sa.select(sa.func.max(t.c.sale_date)).where(market_sale_criteria())
    )).scalar_one_or_none()


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


async def build_neighborhood_summary(conn: AsyncConnection, anchor: date | None) -> int:
    """Grouping and medians run in a worker thread (insert_rows pulls out())."""
    s = ParcelSummary.__table__
    rows = (await conn.execute(
        sa.select(
            s.c.neighborhood, s.c.parcel_class, s.c.last_sale_date, s.c.last_sale_price,
            s.c.price_per_sqft, s.c.occupancy, s.c.year_built, s.c.value_change_pct,
        ).where(s.c.is_active.is_(True), s.c.neighborhood.isnot(None))
    )).all()
    since = (anchor - timedelta(days=730)) if anchor else None

    def out():
        groups: dict[str, list] = defaultdict(list)
        for row in rows:
            groups[row.neighborhood].append(row)
        for code, members in groups.items():
            residential = [m for m in members if m.parcel_class == "R"]
            recent = [
                m for m in members
                if since and m.last_sale_date and m.last_sale_date >= since
                and m.last_sale_price
            ]
            known = [m for m in residential if m.occupancy != "unknown"]
            yield {
                "code": code,
                "parcel_count": len(members),
                "residential_count": len(residential),
                "parcels_sold_24m": len(recent),
                "median_sale_price_24m": _median([m.last_sale_price for m in recent]),
                "median_price_per_sqft_24m": _median(
                    [m.price_per_sqft for m in recent if m.price_per_sqft]
                ),
                "owner_occupied_share": (
                    sum(m.occupancy == "owner_occupied" for m in known) / len(known)
                    if known else None
                ),
                "median_year_built": _median([m.year_built for m in residential if m.year_built]),
                "median_value_change_pct": _median(
                    [m.value_change_pct for m in members if m.value_change_pct is not None]
                ),
            }

    await conn.execute(sa.delete(NeighborhoodSummary.__table__))
    return await insert_rows(conn, NeighborhoodSummary.__table__, out())


async def current_data_version(conn: AsyncConnection) -> int:
    t = DataVersion.__table__
    version = (await conn.execute(sa.select(t.c.version).where(t.c.id == 1))).scalar_one_or_none()
    return version or 0


async def bump_data_version(conn: AsyncConnection) -> int:
    t = DataVersion.__table__
    new = await current_data_version(conn) + 1
    await conn.execute(sa.delete(t))
    await conn.execute(sa.insert(t).values(id=1, version=new, updated_at=datetime.now()))
    return new


async def rebuild_derived(engine: AsyncEngine | None = None) -> int:
    if engine is None:
        from db.engine import engine as default_engine

        engine = default_engine
    async with engine.begin() as conn:
        parcels = await build_parcel_summary(conn)
        await build_owner_index(conn)
        anchor = await latest_sale_date(conn)
        neighborhoods = await build_neighborhood_summary(conn, anchor)
        version = await bump_data_version(conn)
    logger.info("Derived data v%d: %d parcels, %d neighborhoods", version, parcels, neighborhoods)

    from derived.mapbinary import build_map_binary, write_map_binary

    async with engine.connect() as conn:
        data = await build_map_binary(conn, version)
    path = await asyncio.to_thread(write_map_binary, data, version)
    logger.info("Wrote map binary %s (%d KB)", path, len(data) // 1024)
    return version
