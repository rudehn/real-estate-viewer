"""Owner profiles, portfolios and investor-behavior analytics."""
from __future__ import annotations

from datetime import date
from typing import Literal

import sqlalchemy as sa
from pydantic import BaseModel

from api.errors import not_found
from api.filters import Filters, parcel_conditions
from db.county_models import ParcelSummary
from db.models import (
    AcquisitionWave,
    NetSellerStats,
    OwnerProfile,
    OwnerStats,
    OwnerYearActivity,
    Parcel,
    ParcelClass,
    RelatedOwner,
    Transaction,
)
from db.sqlutil import date_add_days
from services.owner_names import merge_owner_rows

# Mailing addresses shared by more owners than this are service addresses
# (title companies, registered agents), not evidence of common ownership.
_MAX_OWNERS_PER_ADDRESS = 12


async def owner_profile(session, owner_name: str) -> OwnerProfile:
    """Activity history and related entities for one owner.

    Aggregated in Python: even the county's biggest investors have a few
    thousand transactions, and the deal grouping / buy-sell pairing logic
    is much clearer here than in portable SQL.
    """
    buys = (
        await session.exec(
            sa.select(Transaction.parcel_id, Transaction.sale_date, Transaction.sale_price)
            .where(Transaction.new_owner == owner_name)
        )
    ).all()
    sells = (
        await session.exec(
            sa.select(Transaction.parcel_id, Transaction.sale_date, Transaction.sale_price)
            .where(Transaction.old_owner == owner_name)
        )
    ).all()

    # Yearly counts, with money totals counted once per deal: portfolio
    # conveyances stamp the whole price on every parcel row.
    years: dict[int, dict[str, float]] = {}

    def bucket(year: int) -> dict[str, float]:
        return years.setdefault(
            year, {"buy_count": 0, "sell_count": 0, "total_spent": 0.0, "total_received": 0.0}
        )

    for rows, count_key, money_key in (
        (buys, "buy_count", "total_spent"),
        (sells, "sell_count", "total_received"),
    ):
        seen_deals: set[tuple] = set()
        for _parcel_id, sale_date, price in rows:
            b = bucket(sale_date.year)
            b[count_key] += 1
            deal = (sale_date, price)
            if deal not in seen_deals:
                seen_deals.add(deal)
                b[money_key] += price or 0.0

    activity = [
        OwnerYearActivity(year=y, **{k: v for k, v in stats.items()})
        for y, stats in sorted(years.items())
    ]

    # Hold periods: pair each sale with the owner's latest prior purchase
    # of the same parcel.
    buys_by_parcel: dict[str, list] = {}
    for parcel_id, sale_date, _ in buys:
        buys_by_parcel.setdefault(parcel_id, []).append(sale_date)
    hold_days: list[int] = []
    for parcel_id, sell_date, _ in sells:
        prior = [d for d in buys_by_parcel.get(parcel_id, []) if d < sell_date]
        if prior:
            hold_days.append((sell_date - max(prior)).days)
    hold_days.sort()
    median_hold = float(hold_days[len(hold_days) // 2]) if hold_days else None

    # Related entities: other owners buying under the same mailing address.
    # sa.select (unlike sqlmodel's select) does not auto-unwrap a single
    # column, so scalars() is called explicitly here.
    addr_rows = (
        await session.exec(
            sa.select(Transaction.mailing_address)
            .where(Transaction.new_owner == owner_name)
            .where(Transaction.mailing_address != "")
            .distinct()
        )
    ).scalars().all()
    related: list[RelatedOwner] = []
    if addr_rows:
        rows = (
            await session.exec(
                sa.select(
                    Transaction.new_owner,
                    Transaction.mailing_address,
                    sa.func.count().label("cnt"),
                )
                .where(Transaction.mailing_address.in_(addr_rows))
                .where(Transaction.new_owner != owner_name)
                .group_by(Transaction.new_owner, Transaction.mailing_address)
                .order_by(sa.desc("cnt"))
            )
        ).all()
        owners_per_addr: dict[str, int] = {}
        for _, addr, _ in rows:
            owners_per_addr[addr] = owners_per_addr.get(addr, 0) + 1
        seen_names: set[str] = set()
        for name, addr, cnt in rows:
            if owners_per_addr[addr] > _MAX_OWNERS_PER_ADDRESS or name in seen_names:
                continue
            seen_names.add(name)
            related.append(
                RelatedOwner(owner_name=name, shared_address=addr, transaction_count=cnt)
            )
            if len(related) >= 20:
                break

    all_dates = [d for _, d, _ in buys] + [d for _, d, _ in sells]
    return OwnerProfile(
        owner_name=owner_name,
        first_activity=min(all_dates) if all_dates else None,
        last_activity=max(all_dates) if all_dates else None,
        total_buys=len(buys),
        total_sells=len(sells),
        median_hold_days=median_hold,
        activity=activity,
        related_owners=related,
    )


async def acquisition_waves(
    session, *, window_days: int = 90, min_acquisitions: int = 5,
    date_from: date | None = None, date_to: date | None = None, limit: int = 50,
) -> list[AcquisitionWave]:
    """Find owners who made many purchases in a short window - bulk acquisitions."""
    # Window starts must be DISTINCT (owner, date) pairs. Joining the raw
    # table against itself multiplied the counts quadratically for owners
    # with many same-day purchases (630 same-day buys => ~397k pairs).
    starts = sa.select(
        Transaction.new_owner.label("owner"),
        Transaction.sale_date.label("start_date"),
    ).distinct()
    if date_from:
        starts = starts.where(Transaction.sale_date >= date_from)
    if date_to:
        starts = starts.where(Transaction.sale_date <= date_to)
    starts = starts.subquery()

    # Aggregate purchases to deals first: a portfolio purchase stamps the
    # whole deal price on every parcel row, so summing raw rows counted a
    # $10M deal hundreds of times. One (owner, date, price) group = one deal
    # of parcel_count parcels.
    deals = (
        sa.select(
            Transaction.new_owner.label("owner"),
            Transaction.sale_date.label("deal_date"),
            Transaction.sale_price.label("deal_price"),
            sa.func.count().label("parcel_count"),
        )
        .group_by(Transaction.new_owner, Transaction.sale_date, Transaction.sale_price)
        .subquery()
    )

    window_end_expr = date_add_days(starts.c.start_date, window_days)
    count_expr = sa.func.sum(deals.c.parcel_count).label("acquisition_count")
    spent_expr = sa.func.sum(deals.c.deal_price).label("total_spent")

    windows = (
        sa.select(
            starts.c.owner.label("owner_name"),
            starts.c.start_date.label("window_start"),
            window_end_expr.label("window_end"),
            count_expr,
            spent_expr,
        )
        .select_from(
            starts.join(
                deals,
                (deals.c.owner == starts.c.owner)
                & (deals.c.deal_date >= starts.c.start_date)
                & (deals.c.deal_date <= window_end_expr),
            )
        )
        .group_by(starts.c.owner, starts.c.start_date)
        .having(count_expr >= min_acquisitions)
        .subquery()
    )

    # Overlapping windows make the same buying spree show up many times;
    # keep only each owner's biggest window.
    ranked = sa.select(
        windows,
        sa.func.row_number()
        .over(
            partition_by=windows.c.owner_name,
            order_by=[sa.desc(windows.c.acquisition_count), windows.c.window_start],
        )
        .label("rn"),
    ).subquery()
    query = (
        sa.select(
            ranked.c.owner_name,
            ranked.c.window_start,
            ranked.c.window_end,
            ranked.c.acquisition_count,
            ranked.c.total_spent,
        )
        .where(ranked.c.rn == 1)
        .order_by(sa.desc(ranked.c.acquisition_count))
        .limit(limit)
    )

    result = await session.exec(query)
    return result.mappings().all()


async def net_sellers(
    session, *, min_net_sells: int = 3, date_from: date | None = None,
    date_to: date | None = None, limit: int = 50,
) -> list[NetSellerStats]:
    """Find entities actively selling off their portfolio (sells >> buys)."""
    buys = sa.select(Transaction.new_owner.label("owner"), sa.func.count().label("buy_count"))
    sells = sa.select(Transaction.old_owner.label("owner"), sa.func.count().label("sell_count"))
    if date_from:
        buys = buys.where(Transaction.sale_date >= date_from)
        sells = sells.where(Transaction.sale_date >= date_from)
    if date_to:
        buys = buys.where(Transaction.sale_date <= date_to)
        sells = sells.where(Transaction.sale_date <= date_to)
    buys = buys.group_by(Transaction.new_owner).subquery()
    sells = sells.group_by(Transaction.old_owner).subquery()

    net_expr = (sells.c.sell_count - sa.func.coalesce(buys.c.buy_count, 0)).label("net")
    query = (
        sa.select(
            sells.c.owner.label("owner_name"),
            sa.func.coalesce(buys.c.buy_count, 0).label("buy_count"),
            sells.c.sell_count,
            net_expr,
        )
        .outerjoin(buys, sells.c.owner == buys.c.owner)
        .where(net_expr >= min_net_sells)
        .order_by(sa.desc(net_expr))
        # Over-fetch: rows are re-merged by normalized owner name below.
        .limit(limit * 3)
    )
    rows = (await session.exec(query)).mappings().all()
    return merge_owner_rows(
        rows,
        sum_fields=("buy_count", "sell_count", "net"),
        limit=limit,
        sort_field="net",
    )


async def absentee_owners(
    session, *, parcel_class: ParcelClass | None = None, limit: int = 50,
) -> list[OwnerStats]:
    """Find owners whose mailing address is outside Ohio - likely absentee/investor owners."""
    query = (
        sa.select(
            Transaction.new_owner.label("owner_name"),
            sa.func.count(Transaction.id).label("transaction_count"),
            sa.func.sum(Transaction.sale_price).label("total_spent"),
            sa.func.avg(Transaction.sale_price).label("avg_price"),
        )
        .where(Transaction.mailing_address != "")
        .where(Transaction.mailing_address.not_like("%OH%"))
        .where(Transaction.mailing_address.not_like("%Ohio%"))
        .group_by(Transaction.new_owner)
        .order_by(sa.desc("transaction_count"))
        .limit(limit)
    )
    if parcel_class:
        query = query.where(Transaction.parcel_class == parcel_class)

    result = await session.exec(query)
    return result.mappings().all()


class OwnerPortfolio(BaseModel):
    owner_name: str
    parcel_count: int
    total_acres: float
    total_market_value: float


class Holding(BaseModel):
    parcel_id: str
    address: str | None
    parcel_class: str
    neighborhood: str | None
    living_sqft: int | None
    year_built: int | None
    market_value: float | None
    last_sale_date: date | None
    last_sale_price: float | None
    occupancy: str
    latitude: float | None
    longitude: float | None


class OwnerDetail(BaseModel):
    owner_name: str
    profile: OwnerProfile
    holdings: list[Holding]
    totals: dict[str, float]


async def top_owners(
    session, f: Filters, *, order_by: Literal["parcels", "acres", "value"], limit: int
) -> list[OwnerPortfolio]:
    ps, p = ParcelSummary.__table__, Parcel.__table__
    count = sa.func.count().label("parcel_count")
    acres = sa.func.coalesce(sa.func.sum(p.c.acres), 0).label("total_acres")
    value = sa.func.coalesce(sa.func.sum(ps.c.market_value), 0).label("total_market_value")
    sort = {"parcels": count, "acres": acres, "value": value}[order_by]
    rows = (await session.exec(
        sa.select(ps.c.owner_name, count, acres, value)
        .select_from(ps).join(p, p.c.parcel_id == ps.c.parcel_id)
        .where(ps.c.owner_name.isnot(None), ps.c.is_active.is_(True), *parcel_conditions(f, ps))
        .group_by(ps.c.owner_name)
        .order_by(sort.desc(), ps.c.owner_name)
        .limit(limit)
    )).mappings().all()
    return [OwnerPortfolio(**r) for r in rows]


async def owner_detail(session, name: str) -> OwnerDetail:
    ps, p = ParcelSummary.__table__, Parcel.__table__
    rows = (await session.exec(
        sa.select(ps.c.parcel_id, ps.c.address, ps.c.parcel_class, ps.c.neighborhood,
                  ps.c.living_sqft, ps.c.year_built, ps.c.market_value, ps.c.last_sale_date,
                  ps.c.last_sale_price, ps.c.occupancy, ps.c.latitude, ps.c.longitude,
                  p.c.acres)
        .select_from(ps).join(p, p.c.parcel_id == ps.c.parcel_id)
        .where(ps.c.owner_name == name, ps.c.is_active.is_(True))
        .order_by(ps.c.address)
    )).mappings().all()
    profile = await owner_profile(session, name)
    if not rows and not profile.total_buys and not profile.total_sells:
        raise not_found(f"Owner {name}")
    holdings = [Holding(**{k: r[k] for k in Holding.model_fields}) for r in rows]
    return OwnerDetail(
        owner_name=name, profile=profile, holdings=holdings,
        totals={
            "parcel_count": len(rows),
            "total_market_value": sum(r["market_value"] or 0 for r in rows),
            "total_acres": sum(r["acres"] or 0 for r in rows),
        },
    )
