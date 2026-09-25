"""Sales list, CSV export and flip detection."""
from __future__ import annotations

import csv
import io
from collections.abc import AsyncIterator
from datetime import date

import sqlalchemy as sa
from pydantic import BaseModel

from api.filters import Filters, sale_conditions
from db.county_models import Neighborhood, ParcelSummary
from db.criteria import market_sale_criteria, plausible_price_criteria, single_parcel_criteria
from db.models import FlipResult, Parcel, ParcelClass, Transaction
from db.sqlutil import days_between

SORTABLE = ("sale_date", "sale_price", "price_per_sqft", "living_sqft")
CSV_COLUMNS = ("sale_date", "sale_price", "address", "buyer", "seller", "parcel_class",
               "neighborhood", "neighborhood_name", "living_sqft", "price_per_sqft",
               "year_built", "beds", "baths", "is_market_sale", "validity", "parcel_id")


class SaleRow(BaseModel):
    id: int
    parcel_id: str
    sale_date: date
    sale_price: float
    address: str | None
    buyer: str
    seller: str
    parcel_class: str
    neighborhood: str | None
    neighborhood_name: str | None
    living_sqft: int | None
    price_per_sqft: float | None
    year_built: int | None
    beds: int | None
    baths: float | None
    is_market_sale: bool
    validity: str | None
    latitude: float | None
    longitude: float | None


class SalesPage(BaseModel):
    total: int
    page: int
    page_size: int
    applied_filters: list[str]
    rows: list[SaleRow]


class FlipsPage(BaseModel):
    applied_filters: list[str]
    rows: list[FlipResult]


def _sales_select(f: Filters, market_only: bool):
    t, ps, p, n = (Transaction.__table__, ParcelSummary.__table__, Parcel.__table__,
                   Neighborhood.__table__)
    ppsf = sa.case((ps.c.living_sqft > 0, t.c.sale_price * 1.0 / ps.c.living_sqft))
    # A market sale: arm's length, a real price, and a per-parcel price (not
    # one row of a multi-parcel deal, flagged or not).
    market = sa.and_(market_sale_criteria(), plausible_price_criteria(), single_parcel_criteria())
    is_market = sa.case((market, True), else_=False)
    conditions = sale_conditions(f, t, ps)
    if market_only:
        conditions.append(market)
    columns = [
        t.c.id, t.c.parcel_id, t.c.sale_date, t.c.sale_price,
        t.c.parcel_location.label("address"), t.c.new_owner.label("buyer"),
        t.c.old_owner.label("seller"), t.c.parcel_class, p.c.neighborhood,
        n.c.name.label("neighborhood_name"), ps.c.living_sqft, ppsf.label("price_per_sqft"),
        ps.c.year_built, ps.c.beds, ps.c.baths, is_market.label("is_market_sale"),
        t.c.sale_validity.label("validity"), ps.c.latitude, ps.c.longitude,
    ]
    base = (
        sa.select(*columns).select_from(t)
        .outerjoin(ps, ps.c.parcel_id == t.c.parcel_id)
        .outerjoin(p, p.c.parcel_id == t.c.parcel_id)
        .outerjoin(n, n.c.code == p.c.neighborhood)
        .where(*conditions)
    )
    sort_columns = {"sale_date": t.c.sale_date, "sale_price": t.c.sale_price,
                    "price_per_sqft": ppsf, "living_sqft": ps.c.living_sqft}
    return base, sort_columns, t.c.id


def _row(mapping) -> dict:
    row = dict(mapping)
    cls = row["parcel_class"]
    row["parcel_class"] = cls.name if isinstance(cls, ParcelClass) else cls
    row["is_market_sale"] = bool(row["is_market_sale"])
    return row


def _ordered(base, sort_columns, tiebreak, sort: str, order: str):
    column = sort_columns[sort]
    direction = column.desc() if order == "desc" else column.asc()
    return base.order_by(sa.nulls_last(direction), tiebreak.desc())


async def list_sales(session, f: Filters, *, sort: str, order: str, page: int, page_size: int,
                     market_only: bool) -> SalesPage:
    base, sort_columns, tiebreak = _sales_select(f, market_only)
    total = (await session.exec(
        sa.select(sa.func.count()).select_from(base.subquery())
    )).scalar_one()
    rows = (await session.exec(
        _ordered(base, sort_columns, tiebreak, sort, order)
        .limit(page_size).offset((page - 1) * page_size)
    )).mappings().all()
    return SalesPage(total=total, page=page, page_size=page_size, applied_filters=f.active(),
                     rows=[SaleRow(**_row(r)) for r in rows])


async def stream_sales_csv(session, f: Filters, *, sort: str, order: str,
                           market_only: bool) -> AsyncIterator[str]:
    base, sort_columns, tiebreak = _sales_select(f, market_only)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    yield buffer.getvalue()
    result = await session.stream(_ordered(base, sort_columns, tiebreak, sort, order))
    async for partition in result.mappings().partitions(2000):
        buffer.seek(0)
        buffer.truncate()
        for mapping in partition:
            row = _row(mapping)
            writer.writerow(["" if row[c] is None else row[c] for c in CSV_COLUMNS])
        yield buffer.getvalue()


async def find_flips(
    session,
    *,
    max_hold_days: int = 730,
    min_profit_pct: float = 0.1,
    min_profit: float = 0.0,
    date_from: date | None = None,
    date_to: date | None = None,
    classes: list[ParcelClass] | None = None,
    limit: int = 50,
) -> list[dict]:
    """Find properties bought and resold quickly at a profit (flips)."""
    # Only single-parcel arm's-length sales with a plausible price qualify on
    # either side: portfolio deals stamp the whole deal price on every parcel
    # row, which would turn a $50k house inside a $25M portfolio sale into a
    # fake 500x flip, and a nominal "buy" resold high would look like a
    # fake flip too.
    sides = (
        sa.select(
            Transaction.parcel_id,
            Transaction.parcel_location,
            Transaction.sale_date,
            Transaction.sale_price,
            Transaction.new_owner,
            Transaction.parcel_class,
            sa.func.count()
            .over(
                partition_by=[
                    Transaction.sale_date,
                    Transaction.new_owner,
                    Transaction.sale_price,
                ]
            )
            .label("deal_size"),
        )
        .where(market_sale_criteria(include_distress=True), plausible_price_criteria())
        .subquery()
    )
    t1 = sides.alias("t1")
    t2 = sides.alias("t2")

    hold_days_expr = days_between(t2.c.sale_date, t1.c.sale_date)
    profit_expr = t2.c.sale_price - t1.c.sale_price
    profit_pct_expr = profit_expr / t1.c.sale_price

    query = (
        sa.select(
            t1.c.parcel_id,
            t1.c.parcel_location,
            t1.c.sale_date.label("buy_date"),
            t2.c.sale_date.label("sell_date"),
            t1.c.sale_price.label("buy_price"),
            t2.c.sale_price.label("sell_price"),
            hold_days_expr.label("hold_days"),
            profit_expr.label("profit"),
            profit_pct_expr.label("profit_pct"),
            t1.c.new_owner.label("buyer"),
            t2.c.new_owner.label("seller"),
        )
        .select_from(t1.join(
            t2, (t1.c.parcel_id == t2.c.parcel_id) & (t2.c.sale_date > t1.c.sale_date)
        ))
        .where(t1.c.deal_size == 1)
        .where(t2.c.deal_size == 1)
        .where(hold_days_expr <= max_hold_days)
        .where(profit_pct_expr >= min_profit_pct)
        .where(profit_expr >= min_profit)
        .order_by(profit_pct_expr.desc())
        .limit(limit)
    )
    if date_from:
        query = query.where(t1.c.sale_date >= date_from)
    if date_to:
        query = query.where(t2.c.sale_date <= date_to)
    if classes:
        query = query.where(t1.c.parcel_class.in_([c.value for c in classes]))

    result = await session.exec(query)
    return [dict(r) for r in result.mappings().all()]
