"""Market summary, trends, top buyers/sellers, and price points.

Median comes from a row_number/count window pair so it works on both SQLite
and Postgres (no percentile_cont on SQLite).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

import sqlalchemy as sa
from pydantic import BaseModel
from sqlalchemy import Select, Subquery

from api.filters import Filters, needs_summary, sale_conditions
from db.county_models import ParcelSummary
from db.criteria import market_sale, single_parcel_criteria
from db.models import MarketStatsBucket, OwnerStats, Parcel, Transaction
from derived.summary import latest_sale_date
from services.owner_names import merge_owner_rows


async def market_buckets(
    session,
    *,
    granularity: Literal["month", "quarter", "year", "all"],
    market_only: bool,
    apply: Callable[[Select], Select],
    with_ppsf: bool = False,
) -> list[MarketStatsBucket]:
    # Portfolio deals are recorded with the full deal price on every parcel
    # row, and the county doesn't always flag them (a $41M, 60-parcel deal is
    # marked plain VALID SALE). Detect them structurally: identical
    # (date, buyer, price) across rows is one conveyance, not N sales.
    deal_rows = sa.select(
        Transaction.sale_date,
        Transaction.sale_price,
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
    if with_ppsf:
        ps = ParcelSummary.__table__
        deal_rows = deal_rows.add_columns(
            sa.case(
                (ps.c.living_sqft > 0, Transaction.sale_price * 1.0 / ps.c.living_sqft)
            ).label("ppsf")
        ).outerjoin(ps, ps.c.parcel_id == Transaction.parcel_id)
    else:
        deal_rows = deal_rows.add_columns(sa.literal(None, type_=sa.Float).label("ppsf"))

    if market_only:
        deal_rows = deal_rows.where(market_sale())
    else:
        deal_rows = deal_rows.where(Transaction.sale_price > 0)
    deal_rows = apply(deal_rows).subquery()

    if granularity == "all":
        year_col = sa.literal(0).label("y")
    else:
        year_col = sa.cast(sa.extract("year", deal_rows.c.sale_date), sa.Integer).label("y")
    month_col = sa.cast(sa.extract("month", deal_rows.c.sale_date), sa.Integer)
    if granularity == "month":
        sub_col = month_col
    elif granularity == "quarter":
        sub_col = sa.case(
            (month_col <= 3, 1), (month_col <= 6, 2), (month_col <= 9, 3), else_=4
        )
    else:
        sub_col = sa.literal(1)
    sub_col = sub_col.label("b")

    base = (
        sa.select(
            year_col,
            sub_col,
            deal_rows.c.sale_price.label("price"),
            deal_rows.c.ppsf.label("ppsf"),
            sa.func.row_number()
            .over(partition_by=[year_col, sub_col], order_by=deal_rows.c.sale_price)
            .label("rn"),
            sa.func.count().over(partition_by=[year_col, sub_col]).label("cnt"),
            sa.func.row_number()
            .over(
                partition_by=[year_col, sub_col],
                order_by=sa.nulls_last(deal_rows.c.ppsf.asc()),
            )
            .label("rn_ppsf"),
            sa.func.count(deal_rows.c.ppsf)
            .over(partition_by=[year_col, sub_col])
            .label("cnt_ppsf"),
        )
        .where(deal_rows.c.deal_size == 1)
        .subquery()
    )

    # The middle row(s) by price within each bucket; avg() of the one or two
    # selected rows is the median. `//` compiles to plain integer division on
    # both dialects, where `/` would emit a float-casting true division.
    is_median_row = sa.or_(
        base.c.rn == (base.c.cnt + 1) // 2,
        base.c.rn == (base.c.cnt + 2) // 2,
    )
    is_median_ppsf_row = sa.or_(
        base.c.rn_ppsf == (base.c.cnt_ppsf + 1) // 2,
        base.c.rn_ppsf == (base.c.cnt_ppsf + 2) // 2,
    )
    query = (
        sa.select(
            base.c.y,
            base.c.b,
            sa.func.count().label("transaction_count"),
            sa.func.avg(sa.case((is_median_row, base.c.price))).label("median_price"),
            sa.func.avg(base.c.price).label("avg_price"),
            sa.func.sum(base.c.price).label("total_volume"),
            sa.func.avg(sa.case((is_median_ppsf_row, base.c.ppsf))).label("median_ppsf"),
        )
        .group_by(base.c.y, base.c.b)
        .order_by(base.c.y, base.c.b)
    )
    rows = (await session.exec(query)).mappings().all()

    buckets = []
    for row in rows:
        y, b = row["y"], row["b"]
        if granularity == "all":
            period, start = "all", date(1970, 1, 1)
        elif granularity == "month":
            period, start = f"{y}-{b:02d}", date(y, b, 1)
        elif granularity == "quarter":
            period, start = f"{y}-Q{b}", date(y, 3 * (b - 1) + 1, 1)
        else:
            period, start = str(y), date(y, 1, 1)
        buckets.append(
            MarketStatsBucket(
                period=period,
                period_start=start,
                transaction_count=row["transaction_count"],
                median_price=row["median_price"] or 0.0,
                avg_price=row["avg_price"] or 0.0,
                total_volume=row["total_volume"] or 0.0,
                median_price_per_sqft=row["median_ppsf"],
            )
        )
    return buckets


async def top_buyers(
    session, *, limit: int = 10, min_spent: float = 0.0, market_only: bool = True,
    date_from: date | None = None, date_to: date | None = None,
) -> list[OwnerStats]:
    query = (
        sa.select(
            Transaction.new_owner.label("owner_name"),
            sa.func.count(Transaction.id).label("transaction_count"),
            sa.func.sum(Transaction.sale_price).label("total_spent"),
            sa.func.avg(Transaction.sale_price).label("avg_price"),
        )
        .where(Transaction.sale_price >= min_spent)
        .group_by(Transaction.new_owner)
        .order_by(sa.desc("transaction_count"))
        # Over-fetch: rows are re-merged by normalized owner name below.
        .limit(limit * 3)
    )
    if market_only:
        query = query.where(market_sale(include_multi_parcel=True))
    if date_from:
        query = query.where(Transaction.sale_date >= date_from)
    if date_to:
        query = query.where(Transaction.sale_date <= date_to)

    rows = (await session.exec(query)).mappings().all()
    merged = merge_owner_rows(rows, sum_fields=("transaction_count", "total_spent"), limit=limit)
    for r in merged:
        r["avg_price"] = r["total_spent"] / r["transaction_count"] if r["transaction_count"] else 0
    return merged


async def top_sellers(
    session, *, limit: int = 10, market_only: bool = True,
    date_from: date | None = None, date_to: date | None = None,
) -> list[OwnerStats]:
    query = (
        sa.select(
            Transaction.old_owner.label("owner_name"),
            sa.func.count(Transaction.id).label("transaction_count"),
            sa.func.sum(Transaction.sale_price).label("total_spent"),
            sa.func.avg(Transaction.sale_price).label("avg_price"),
        )
        .group_by(Transaction.old_owner)
        .order_by(sa.desc("transaction_count"))
        # Over-fetch: rows are re-merged by normalized owner name below.
        .limit(limit * 3)
    )
    if market_only:
        query = query.where(market_sale(include_multi_parcel=True))
    if date_from:
        query = query.where(Transaction.sale_date >= date_from)
    if date_to:
        query = query.where(Transaction.sale_date <= date_to)
    rows = (await session.exec(query)).mappings().all()
    merged = merge_owner_rows(rows, sum_fields=("transaction_count", "total_spent"), limit=limit)
    for r in merged:
        r["avg_price"] = r["total_spent"] / r["transaction_count"] if r["transaction_count"] else 0
    return merged


class WindowStats(BaseModel):
    label: str
    start: date
    end: date
    stats: MarketStatsBucket | None


class MarketSummary(BaseModel):
    applied_filters: list[str]
    anchor_date: date | None
    totals: MarketStatsBucket | None
    current: WindowStats | None
    prior: WindowStats | None


def _apply_filters(f: Filters, *, join_summary: bool):
    t, ps = Transaction.__table__, ParcelSummary.__table__

    def apply(stmt):
        if join_summary:
            stmt = stmt.outerjoin(ps, ps.c.parcel_id == t.c.parcel_id)
        return stmt.where(*sale_conditions(f, t, ps))

    return apply


def _label(start: date, end: date) -> str:
    return f"{start:%b %Y} - {end:%b %Y}"


async def market_summary(session, f: Filters) -> MarketSummary:
    anchor = await latest_sale_date(await session.connection())
    apply = _apply_filters(f, join_summary=needs_summary(f))
    totals = await market_buckets(session, granularity="all", market_only=True, apply=apply)
    if anchor is None:
        return MarketSummary(applied_filters=f.active(), anchor_date=None,
                             totals=totals[0] if totals else None, current=None, prior=None)
    windows = []
    current_start = anchor - timedelta(days=364)
    previous_end = current_start - timedelta(days=1)
    for start, end in ((current_start, anchor),
                       (previous_end - timedelta(days=364), previous_end)):
        window_filters = f.model_copy(update={"date_from": start, "date_to": end})
        buckets = await market_buckets(
            session, granularity="all", market_only=True,
            apply=_apply_filters(window_filters, join_summary=needs_summary(f)),
        )
        windows.append(WindowStats(label=_label(start, end), start=start, end=end,
                                   stats=buckets[0] if buckets else None))
    return MarketSummary(applied_filters=f.active(), anchor_date=anchor,
                         totals=totals[0] if totals else None,
                         current=windows[0], prior=windows[1])


async def market_trends(session, f: Filters, granularity: str) -> list[MarketStatsBucket]:
    # with_ppsf joins parcel_summary itself, so apply only adds conditions.
    return await market_buckets(session, granularity=granularity, market_only=True,
                                apply=_apply_filters(f, join_summary=False), with_ppsf=True)


class PricePoint(BaseModel):
    parcel_id: str
    sale_date: date
    sale_price: float
    parcel_class: str


async def price_points(session, f: Filters, limit: int) -> tuple[int, list[PricePoint]]:
    t, ps = Transaction.__table__, ParcelSummary.__table__
    base = sa.select(t.c.parcel_id, t.c.sale_date, t.c.sale_price, t.c.parcel_class)
    if needs_summary(f):
        base = base.outerjoin(ps, ps.c.parcel_id == t.c.parcel_id)
    base = base.where(market_sale(), single_parcel_criteria(), *sale_conditions(f, t, ps))
    total = (await session.exec(
        sa.select(sa.func.count()).select_from(base.subquery())
    )).scalar_one()
    rows = (await session.exec(base.order_by(sa.func.random()).limit(limit))).all()
    points = [PricePoint(parcel_id=r.parcel_id, sale_date=r.sale_date, sale_price=r.sale_price,
                         parcel_class=r.parcel_class.name) for r in rows]
    return total, sorted(points, key=lambda p: p.sale_date)


@dataclass
class GroupStats:
    count: int
    median: float | None
    total: float | None


async def medians_by_group(
    session, rows: Subquery, groups: list[str], value: str
) -> dict[tuple, GroupStats]:
    """Count, median and sum of ``value`` per group, portable to SQLite and Postgres.

    NULL values sort last and are not counted, so the middle row numbers land
    on real values.
    """
    keys = [rows.c[g] for g in groups]
    v = rows.c[value]
    ranked = sa.select(
        *[k.label(f"g{i}") for i, k in enumerate(keys)], v.label("v"),
        sa.func.row_number().over(partition_by=keys, order_by=sa.nulls_last(v.asc())).label("rn"),
        sa.func.count(v).over(partition_by=keys).label("cnt"),
    ).subquery()
    group_cols = [ranked.c[f"g{i}"] for i in range(len(keys))]
    middle = sa.or_(ranked.c.rn == (ranked.c.cnt + 1) // 2, ranked.c.rn == (ranked.c.cnt + 2) // 2)
    query = sa.select(
        *group_cols, sa.func.count(ranked.c.v), sa.func.avg(sa.case((middle, ranked.c.v))),
        sa.func.sum(ranked.c.v),
    ).group_by(*group_cols)
    out = {}
    for row in (await session.exec(query)).all():
        *key, count, median, total = row
        out[tuple(key)] = GroupStats(count=count, median=median, total=total)
    return out


def market_sale_rows(f: Filters, *, extra_columns: tuple = ()) -> Subquery:
    t, ps, p = Transaction.__table__, ParcelSummary.__table__, Parcel.__table__
    ppsf = sa.case((ps.c.living_sqft > 0, t.c.sale_price * 1.0 / ps.c.living_sqft))
    return (
        sa.select(
            t.c.parcel_id, p.c.neighborhood,
            sa.cast(sa.extract("year", t.c.sale_date), sa.Integer).label("year"),
            t.c.sale_price, ppsf.label("ppsf"), *extra_columns,
        )
        .select_from(t)
        .join(p, p.c.parcel_id == t.c.parcel_id)
        .outerjoin(ps, ps.c.parcel_id == t.c.parcel_id)
        .where(market_sale(), single_parcel_criteria(), *sale_conditions(f, t, ps))
        .subquery()
    )
