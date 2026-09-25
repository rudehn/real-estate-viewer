"""Distressed sales and stale parcels."""
from __future__ import annotations

from datetime import date

import sqlalchemy as sa

from db.criteria import market_sale_criteria, plausible_price_criteria
from db.models import ParcelClass, Transaction
from db.sqlutil import days_between


async def distressed_sales(
    session,
    *,
    max_ratio: float = 0.7,
    min_assessed: int = 10000,
    date_from: date | None = None,
    date_to: date | None = None,
    classes: list[ParcelClass] | None = None,
    limit: int = 50,
) -> list[dict]:
    """Find sales where the price was significantly below assessed value."""
    ratio_expr = (Transaction.sale_price / Transaction.assessed_total).label("assessed_ratio")
    # Nominal/family transfers are excluded (they're cheap by construction,
    # not distressed) but foreclosures and liquidations are kept - those are
    # exactly the distress signal this view exists to surface.
    query = (
        sa.select(
            Transaction.id,
            Transaction.parcel_id,
            Transaction.parcel_location,
            Transaction.sale_date,
            Transaction.sale_price,
            Transaction.assessed_total,
            ratio_expr,
            Transaction.new_owner,
            Transaction.neighborhood,
            Transaction.parcel_class,
        )
        .where(market_sale_criteria(include_distress=True), plausible_price_criteria())
        .where(Transaction.assessed_total >= min_assessed)
        .where(Transaction.sale_price / Transaction.assessed_total <= max_ratio)
        .order_by(ratio_expr)
        .limit(limit)
    )
    if date_from:
        query = query.where(Transaction.sale_date >= date_from)
    if date_to:
        query = query.where(Transaction.sale_date <= date_to)
    if classes:
        query = query.where(Transaction.parcel_class.in_(classes))

    result = await session.exec(query)
    return [dict(r) for r in result.mappings().all()]


async def stale_parcels(
    session,
    *,
    min_years: float = 10.0,
    classes: list[ParcelClass] | None = None,
    limit: int = 50,
) -> list[dict]:
    """Find parcels that haven't changed hands recently."""
    years_expr = (
        days_between(sa.func.current_date(), sa.func.max(Transaction.sale_date)) / 365.25
    )
    query = (
        sa.select(
            Transaction.parcel_id,
            # Aggregated so Postgres accepts the GROUP BY (one row per parcel);
            # a parcel's location/class are consistent across its transactions.
            sa.func.max(Transaction.parcel_location).label("parcel_location"),
            sa.func.max(Transaction.parcel_class).label("parcel_class"),
            sa.func.max(Transaction.sale_date).label("last_sale_date"),
            sa.func.max(Transaction.sale_price).label("last_sale_price"),
            years_expr.label("years_since_sale"),
        )
        .group_by(Transaction.parcel_id)
        .having(years_expr >= min_years)
        .order_by(sa.desc(years_expr))
        .limit(limit)
    )
    if classes:
        query = query.where(Transaction.parcel_class.in_(classes))

    result = await session.exec(query)
    return [dict(r) for r in result.mappings().all()]
