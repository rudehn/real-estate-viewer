
import asyncio
import os
from enum import Enum
from typing import Literal
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path as FilePath

from fastapi import Depends, FastAPI, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlmodel import Field, Session, and_, select, desc
from sqlmodel.ext.asyncio.session import AsyncSession
# from fastapi_filters import create_filters, create_filters_from_model, FilterValues
# from fastapi_filters.ext.sqlalchemy import apply_filters
from sqlalchemy import func, Integer, cast, Date, extract, case, literal, or_
from sqlalchemy.orm import selectinload

from fastapi_filter import FilterDepends, with_prefix
from fastapi_filter.contrib.sqlalchemy import Filter

from db.criteria import MIN_MARKET_PRICE, market_sale_criteria
from db.engine import engine, get_session, init_db
from db.sqlutil import date_add_days, days_between
from services.owner_names import merge_owner_rows
from db.models import (
    OwnerStats, NeighborhoodStats, Transaction, DataFile, TransactionListModel,
    Parcel, ParcelListModel, ParcelClass,
    FlipResult, DistressedSale, OwnerHoldings, NetSellerStats,
    NeighborhoodTrend, StaleParcel, AcquisitionWave, OwnerParcel,
    MarketStatsBucket, OwnerProfile, OwnerYearActivity, RelatedOwner,
    CompSale, ParcelComps, DataHealth,
)
from logging_config import get_logger, configure_logging

configure_logging()
logger = get_logger(__name__)

# Directory of CSV files ingested on startup. Overridable via DATA_DIR so the
# container can point at a mounted volume (default: repo-local src/../data).
DATA_DIR = FilePath(os.getenv("DATA_DIR", str(FilePath(__file__).parent.parent / "data")))

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Server is starting...")
    await init_db()
    from db.maintenance import ensure_transaction_dedup
    await ensure_transaction_dedup()
    logger.info("Database tables ready.")

    # When AUTO_INGEST is enabled (production), self-populate the DB in the
    # background: scrape the county site, ingest, and geocode on a repeating
    # schedule. Runs as a task so the API starts serving immediately.
    ingest_task = None
    if os.getenv("AUTO_INGEST", "false").lower() in ("1", "true", "yes", "on"):
        from services.populate import run_population_loop
        logger.info("AUTO_INGEST enabled; starting background population loop.")
        ingest_task = asyncio.create_task(run_population_loop())

    yield

    if ingest_task is not None:
        ingest_task.cancel()
        try:
            await ingest_task
        except asyncio.CancelledError:
            pass
    logger.info("Server is stopping")

app = FastAPI(
    title="Nate's Real Estate API",
    description="This is a simple api for learning",
    version="0.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# https://go.mcohio.org/applications/treasurer/search/data/Yearly/SALES_2025.zip
# https://go.mcohio.org/applications/treasurer/search/fdpopup.cfm?dtype=YS

# https://testdriven.io/blog/fastapi-sqlmodel/
# https://github.com/arthurio/fastapi-filter/blob/main/examples/fastapi_filter_sqlalchemy.py

class TransactionFilter(Filter):
    # --- 1. Text Search ---
    parcel_id: str | None = None
    new_owner__ilike: str | None = None
    
    # --- 2. Date Ranges (CRITICAL FOR DASHBOARD) ---
    sale_date__gte: date | None = None
    sale_date__lte: date | None = None

    # --- 3. Financial Filtering ---
    sale_price__gte: float | None = None
    sale_price__lte: float | None = None
    
    # --- 4. Property Characteristics ---
    acres__gte: float | None = None
    acres__lte: float | None = None
    parcel_class: ParcelClass | None = None
    parcel_class__in: list[ParcelClass] | None = None

    # --- 6. Sorting ---
    order_by: list[str] | None = ["-sale_date"]

    class Constants(Filter.Constants):
        model = Transaction

class ParcelFilter(Filter):
    acres: int | None = None
    acres__gte: int | None = None
    acres__lte: int | None = None
    parcel_class: ParcelClass | None = None
    # acres_gte: int | None = Field(Query(default=None, description="this is nice"))
    # new_owner__ilike: str | None = None
    # new_owner__like: str | None = None
    class Constants(Filter.Constants):
        model = Parcel 
        # search_model_fields = ["name"]


@app.get("/parcels", response_model=ParcelListModel)
async def get_parcels(offset: int = 0, limit: int = 50,
                     filters: ParcelFilter = FilterDepends(ParcelFilter),
                     session: AsyncSession = Depends(get_session)):
    query = select(Parcel).offset(offset).limit(limit)
    query = filters.filter(query)
    result = await session.exec(query)
    parcels = result.all()

    count_query = select(func.count()).select_from(Parcel)
    count_query = filters.filter(count_query)
    count_result = await session.exec(count_query)
    count = count_result.one()
    return ParcelListModel(count=count, entities=parcels)

# @app.get("/transactions", response_model=list[RealEstateTransaction])
@app.get("/transactions", response_model=TransactionListModel)
async def get_transactions(offset: int = 0, limit: int = 50, is_geocoded: bool = False,
                     filters: TransactionFilter = FilterDepends(TransactionFilter),
                     session: AsyncSession = Depends(get_session)):
    # 1. Start building the select statement
    statement = select(Transaction)


    # 2. EAGER LOADING (Crucial Fix)
    # This tells SQLModel to actually fetch the related Parcel data 
    # so it appears in the nested 'parcel' field of the response.
    statement = statement.options(selectinload(Transaction.parcel))

    # 2. Apply filtering and ordering from fastapi-filter (for Transaction fields).
    # Without an explicit sort the limit-capped result set is arbitrary rows.
    statement = filters.filter(statement)
    statement = filters.sort(statement)
     # 4. Apply Geocoding Filter
    if is_geocoded:
        statement = statement.join(Parcel, Transaction.parcel_id == Parcel.parcel_id).where(
            and_(
                Parcel.latitude.is_not(None),
                Parcel.latitude != 0.0,
                Parcel.longitude.is_not(None),
            )
        )

    # 4. Execute the count query (must operate on the filtered statement)
    # We select the count from the filtered statement's subquery
    count_statement = select(func.count()).select_from(statement.subquery())
    total_count = (await session.exec(count_statement)).one()

    # 5. Apply limit and offset for the final data retrieval
    statement = statement.limit(limit).offset(offset)
    result = await session.exec(statement)
    transactions = result.all()

    return TransactionListModel(entities=transactions, count=total_count)

@app.get("/transactions/{transaction_id}", response_model=Transaction)
def get_transaction(transaction_id: int, session: AsyncSession = Depends(get_session)):
    transaction = session.get(Transaction, transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Not Found")
    return transaction


@app.get("/analytics/market-stats", response_model=list[MarketStatsBucket])
async def get_market_stats(
    granularity: Literal["month", "quarter", "year", "all"] = "year",
    market_only: bool = Query(True, description="Restrict to arm's-length single-parcel sales"),
    filters: TransactionFilter = FilterDepends(TransactionFilter),
    session: AsyncSession = Depends(get_session),
):
    """Price/volume statistics per time bucket, aggregated in SQL.

    Median comes from a row_number/count window pair so it works on both
    SQLite and Postgres (no percentile_cont on SQLite).
    """
    # Portfolio deals are recorded with the full deal price on every parcel
    # row, and the county doesn't always flag them (a $41M, 60-parcel deal is
    # marked plain VALID SALE). Detect them structurally: identical
    # (date, buyer, price) across rows is one conveyance, not N sales.
    deal_rows = select(
        Transaction.sale_date,
        Transaction.sale_price,
        func.count()
        .over(
            partition_by=[
                Transaction.sale_date,
                Transaction.new_owner,
                Transaction.sale_price,
            ]
        )
        .label("deal_size"),
    )
    if market_only:
        deal_rows = deal_rows.where(market_sale_criteria())
    else:
        deal_rows = deal_rows.where(Transaction.sale_price > 0)
    deal_rows = filters.filter(deal_rows).subquery()

    if granularity == "all":
        year_col = literal(0).label("y")
    else:
        year_col = cast(extract("year", deal_rows.c.sale_date), Integer).label("y")
    month_col = cast(extract("month", deal_rows.c.sale_date), Integer)
    if granularity == "month":
        sub_col = month_col
    elif granularity == "quarter":
        sub_col = case(
            (month_col <= 3, 1), (month_col <= 6, 2), (month_col <= 9, 3), else_=4
        )
    else:
        sub_col = literal(1)
    sub_col = sub_col.label("b")

    base = (
        select(
            year_col,
            sub_col,
            deal_rows.c.sale_price.label("price"),
            func.row_number()
            .over(partition_by=[year_col, sub_col], order_by=deal_rows.c.sale_price)
            .label("rn"),
            func.count().over(partition_by=[year_col, sub_col]).label("cnt"),
        )
        .where(deal_rows.c.deal_size == 1)
        .subquery()
    )

    # The middle row(s) by price within each bucket; avg() of the one or two
    # selected rows is the median. `//` compiles to plain integer division on
    # both dialects, where `/` would emit a float-casting true division.
    is_median_row = or_(
        base.c.rn == (base.c.cnt + 1) // 2,
        base.c.rn == (base.c.cnt + 2) // 2,
    )
    query = (
        select(
            base.c.y,
            base.c.b,
            func.count().label("transaction_count"),
            func.avg(case((is_median_row, base.c.price))).label("median_price"),
            func.avg(base.c.price).label("avg_price"),
            func.sum(base.c.price).label("total_volume"),
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
            )
        )
    return buckets


@app.get("/analytics/top-buyers", response_model=list[OwnerStats])
async def get_top_buyers(
    limit: int = 10,
    min_spent: float = 0,
    market_only: bool = Query(True, description="Restrict to arm's-length sales"),
    session: AsyncSession = Depends(get_session)
):
    """
    Finds entities who have purchased the most properties or spent the most money.
    Useful for finding investors or 'Whales'.
    """
    query = (
        select(
            Transaction.new_owner.label("owner_name"),
            func.count(Transaction.id).label("transaction_count"),
            func.sum(Transaction.sale_price).label("total_spent"),
            func.avg(Transaction.sale_price).label("avg_price")
        )
        .where(Transaction.sale_price >= min_spent)
        .group_by(Transaction.new_owner)
        .order_by(desc("transaction_count")) # Sort by volume
        # .order_by(desc("total_spent"))       # OR Sort by money spent
        # Over-fetch: rows are re-merged by normalized owner name below.
        .limit(limit * 3)
    )
    if market_only:
        query = query.where(market_sale_criteria(include_multi_parcel=True))

    rows = (await session.exec(query)).mappings().all()
    merged = merge_owner_rows(rows, sum_fields=("transaction_count", "total_spent"), limit=limit)
    for r in merged:
        r["avg_price"] = r["total_spent"] / r["transaction_count"] if r["transaction_count"] else 0
    return merged

@app.get("/analytics/top-sellers", response_model=list[OwnerStats])
async def get_top_sellers(
    limit: int = 10,
    market_only: bool = Query(True, description="Restrict to arm's-length sales"),
    session: AsyncSession = Depends(get_session),
):
    """Finds entities who are selling off large portfolios."""
    query = (
        select(
            Transaction.old_owner.label("owner_name"),
            func.count(Transaction.id).label("transaction_count"),
            func.sum(Transaction.sale_price).label("total_spent"),
            func.avg(Transaction.sale_price).label("avg_price")
        )
        .group_by(Transaction.old_owner)
        .order_by(desc("transaction_count"))
        # Over-fetch: rows are re-merged by normalized owner name below.
        .limit(limit * 3)
    )
    if market_only:
        query = query.where(market_sale_criteria(include_multi_parcel=True))
    rows = (await session.exec(query)).mappings().all()
    merged = merge_owner_rows(rows, sum_fields=("transaction_count", "total_spent"), limit=limit)
    for r in merged:
        r["avg_price"] = r["total_spent"] / r["transaction_count"] if r["transaction_count"] else 0
    return merged

@app.get("/analytics/neighborhoods", response_model=list[NeighborhoodStats])
async def get_neighborhood_stats(
    limit: int = Query(50, description="Max neighborhoods to return"),
    min_transactions: int = Query(1, description="Minimum transaction count to include"),
    sale_date__gte: date | None = None,
    sale_date__lte: date | None = None,
    parcel_class: ParcelClass | None = None,
    market_only: bool = Query(True, description="Restrict to arm's-length single-parcel sales"),
    session: AsyncSession = Depends(get_session),
):
    """Aggregate sales statistics grouped by neighborhood code."""
    query = (
        select(
            Transaction.neighborhood.label("neighborhood"),
            func.count(Transaction.id).label("transaction_count"),
            func.sum(Transaction.sale_price).label("total_volume"),
            func.avg(Transaction.sale_price).label("avg_price"),
            func.min(Transaction.sale_price).label("min_price"),
            func.max(Transaction.sale_price).label("max_price"),
        )
        .where(Transaction.neighborhood.is_not(None))
        .where(market_sale_criteria() if market_only else Transaction.sale_price > 0)
        .group_by(Transaction.neighborhood)
        .having(func.count(Transaction.id) >= min_transactions)
        .order_by(desc("transaction_count"))
        .limit(limit)
    )
    if sale_date__gte:
        query = query.where(Transaction.sale_date >= sale_date__gte)
    if sale_date__lte:
        query = query.where(Transaction.sale_date <= sale_date__lte)
    if parcel_class:
        query = query.where(Transaction.parcel_class == parcel_class)

    result = await session.exec(query)
    return result.all()


@app.get("/parcels/{parcel_id}/history", response_model=list[Transaction])
async def get_parcel_history(parcel_id: str, session: AsyncSession = Depends(get_session)):
    """View the full sales history of a specific parcel to spot 'Flips'."""
    query = select(Transaction).where(Transaction.parcel_id == parcel_id).order_by(Transaction.sale_date.desc())
    result = await session.exec(query)
    return result.all()


@app.get("/analytics/flips", response_model=list[FlipResult])
async def get_flips(
    max_hold_days: int = Query(730, description="Max days between buy and sell to qualify as a flip"),
    min_profit_pct: float = Query(0.1, description="Minimum profit percentage (0.1 = 10%)"),
    min_profit: float = Query(0, description="Minimum absolute profit in dollars"),
    sale_date__gte: date | None = None,
    sale_date__lte: date | None = None,
    parcel_class: ParcelClass | None = None,
    limit: int = Query(50, le=500),
    session: AsyncSession = Depends(get_session),
):
    """Find properties bought and resold quickly at a profit (flips)."""
    # Only single-parcel arm's-length sales qualify on either side: portfolio
    # deals stamp the whole deal price on every parcel row, which would turn
    # a $50k house inside a $25M portfolio sale into a fake 500x flip.
    sides = (
        select(
            Transaction.parcel_id,
            Transaction.parcel_location,
            Transaction.sale_date,
            Transaction.sale_price,
            Transaction.new_owner,
            Transaction.parcel_class,
            func.count()
            .over(
                partition_by=[
                    Transaction.sale_date,
                    Transaction.new_owner,
                    Transaction.sale_price,
                ]
            )
            .label("deal_size"),
        )
        .where(market_sale_criteria(include_distress=True))
        .subquery()
    )
    t1 = sides.alias("t1")
    t2 = sides.alias("t2")

    hold_days_expr = days_between(t2.c.sale_date, t1.c.sale_date)
    profit_expr = t2.c.sale_price - t1.c.sale_price
    profit_pct_expr = profit_expr / t1.c.sale_price

    query = (
        select(
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
        .select_from(t1.join(t2, (t1.c.parcel_id == t2.c.parcel_id) & (t2.c.sale_date > t1.c.sale_date)))
        .where(t1.c.deal_size == 1)
        .where(t2.c.deal_size == 1)
        .where(hold_days_expr <= max_hold_days)
        .where(profit_pct_expr >= min_profit_pct)
        .where(profit_expr >= min_profit)
        .order_by(desc(profit_pct_expr))
        .limit(limit)
    )
    if sale_date__gte:
        query = query.where(t1.c.sale_date >= sale_date__gte)
    if sale_date__lte:
        query = query.where(t2.c.sale_date <= sale_date__lte)
    if parcel_class:
        query = query.where(t1.c.parcel_class == parcel_class.value)

    result = await session.exec(query)
    return result.mappings().all()


@app.get("/analytics/distressed", response_model=list[DistressedSale])
async def get_distressed_sales(
    max_ratio: float = Query(0.7, description="Max sale_price/assessed_total ratio"),
    min_assessed: int = Query(10000, description="Min assessed value to filter out noise"),
    sale_date__gte: date | None = None,
    sale_date__lte: date | None = None,
    parcel_class: ParcelClass | None = None,
    limit: int = Query(50, le=500),
    session: AsyncSession = Depends(get_session),
):
    """Find sales where the price was significantly below assessed value."""
    ratio_expr = (Transaction.sale_price / Transaction.assessed_total).label("assessed_ratio")
    # Nominal/family transfers are excluded (they're cheap by construction,
    # not distressed) but foreclosures and liquidations are kept — those are
    # exactly the distress signal this view exists to surface.
    query = (
        select(
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
        .where(market_sale_criteria(include_distress=True))
        .where(Transaction.assessed_total >= min_assessed)
        .where(Transaction.sale_price / Transaction.assessed_total <= max_ratio)
        .order_by(ratio_expr)
        .limit(limit)
    )
    if sale_date__gte:
        query = query.where(Transaction.sale_date >= sale_date__gte)
    if sale_date__lte:
        query = query.where(Transaction.sale_date <= sale_date__lte)
    if parcel_class:
        query = query.where(Transaction.parcel_class == parcel_class)

    result = await session.exec(query)
    return result.mappings().all()


@app.get("/analytics/absentee-owners", response_model=list[OwnerStats])
async def get_absentee_owners(
    parcel_class: ParcelClass | None = None,
    limit: int = Query(50, le=500),
    session: AsyncSession = Depends(get_session),
):
    """Find owners whose mailing address is outside Ohio — likely absentee/investor owners."""
    query = (
        select(
            Transaction.new_owner.label("owner_name"),
            func.count(Transaction.id).label("transaction_count"),
            func.sum(Transaction.sale_price).label("total_spent"),
            func.avg(Transaction.sale_price).label("avg_price"),
        )
        .where(Transaction.mailing_address != "")
        .where(Transaction.mailing_address.not_like("%OH%"))
        .where(Transaction.mailing_address.not_like("%Ohio%"))
        .group_by(Transaction.new_owner)
        .order_by(desc("transaction_count"))
        .limit(limit)
    )
    if parcel_class:
        query = query.where(Transaction.parcel_class == parcel_class)

    result = await session.exec(query)
    return result.all()


@app.get("/analytics/top-owners", response_model=list[OwnerHoldings])
async def get_top_owners(
    limit: int = Query(50, le=500),
    parcel_class: ParcelClass | None = None,
    order_by: str = Query("count", description="Sort field: count | acres | value"),
    session: AsyncSession = Depends(get_session),
):
    """Current top property owners based on most recent transaction per parcel."""
    # Window function ranks each parcel's transactions newest-first in a single pass —
    # much faster than the double-subquery / self-join approach on large tables.
    ranked = (
        select(
            Transaction.parcel_id,
            Transaction.new_owner,
            Transaction.acres,
            Transaction.assessed_total,
            Transaction.parcel_class,
            func.row_number()
            .over(partition_by=Transaction.parcel_id, order_by=desc(Transaction.sale_date))
            .label("rn"),
        )
        .subquery()
    )

    sort_col = {
        "acres": desc(func.sum(ranked.c.acres)),
        "value": desc(func.coalesce(func.sum(ranked.c.assessed_total), 0)),
    }.get(order_by, desc(func.count(ranked.c.parcel_id)))

    query = (
        select(
            ranked.c.new_owner.label("owner_name"),
            func.count(ranked.c.parcel_id).label("parcel_count"),
            func.sum(ranked.c.acres).label("total_acres"),
            func.coalesce(func.sum(ranked.c.assessed_total), 0).label("total_assessed_value"),
        )
        .where(ranked.c.rn == 1)
        .group_by(ranked.c.new_owner)
        .order_by(sort_col)
        # Over-fetch: rows are re-merged by normalized owner name below.
        .limit(limit * 3)
    )
    if parcel_class:
        query = query.where(ranked.c.parcel_class == parcel_class.value)

    rows = (await session.exec(query)).mappings().all()
    sort_field = {
        "acres": "total_acres",
        "value": "total_assessed_value",
    }.get(order_by, "parcel_count")
    return merge_owner_rows(
        rows,
        sum_fields=("parcel_count", "total_acres", "total_assessed_value"),
        limit=limit,
        sort_field=sort_field,
    )


@app.get("/analytics/net-sellers", response_model=list[NetSellerStats])
async def get_net_sellers(
    min_net_sells: int = Query(3, description="Minimum excess of sells over buys"),
    sale_date__gte: date | None = None,
    sale_date__lte: date | None = None,
    limit: int = Query(50, le=500),
    session: AsyncSession = Depends(get_session),
):
    """Find entities actively selling off their portfolio (sells >> buys)."""
    buys = select(Transaction.new_owner.label("owner"), func.count().label("buy_count"))
    sells = select(Transaction.old_owner.label("owner"), func.count().label("sell_count"))
    if sale_date__gte:
        buys = buys.where(Transaction.sale_date >= sale_date__gte)
        sells = sells.where(Transaction.sale_date >= sale_date__gte)
    if sale_date__lte:
        buys = buys.where(Transaction.sale_date <= sale_date__lte)
        sells = sells.where(Transaction.sale_date <= sale_date__lte)
    buys = buys.group_by(Transaction.new_owner).subquery()
    sells = sells.group_by(Transaction.old_owner).subquery()

    net_expr = (sells.c.sell_count - func.coalesce(buys.c.buy_count, 0)).label("net")
    query = (
        select(
            sells.c.owner.label("owner_name"),
            func.coalesce(buys.c.buy_count, 0).label("buy_count"),
            sells.c.sell_count,
            net_expr,
        )
        .outerjoin(buys, sells.c.owner == buys.c.owner)
        .where(net_expr >= min_net_sells)
        .order_by(desc(net_expr))
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


@app.get("/analytics/neighborhoods/trends", response_model=list[NeighborhoodTrend])
async def get_neighborhood_trends(
    neighborhood: str | None = Query(None, description="Filter to a single neighborhood code"),
    min_transactions: int = Query(5, description="Min transactions per year to include"),
    session: AsyncSession = Depends(get_session),
):
    """Year-over-year median price change per neighborhood (gentrification score).

    Median, not average: one large commercial sale would otherwise define a
    whole neighborhood's year.
    """
    year_expr = cast(extract("year", Transaction.sale_date), Integer).label("year")
    priced = (
        select(
            Transaction.neighborhood.label("neighborhood"),
            year_expr,
            Transaction.sale_price.label("price"),
            func.row_number()
            .over(
                partition_by=[Transaction.neighborhood, year_expr],
                order_by=Transaction.sale_price,
            )
            .label("rn"),
            func.count()
            .over(partition_by=[Transaction.neighborhood, year_expr])
            .label("cnt"),
        )
        .where(Transaction.neighborhood.is_not(None))
        .where(market_sale_criteria())
        .subquery()
    )
    is_median_row = or_(
        priced.c.rn == (priced.c.cnt + 1) // 2,
        priced.c.rn == (priced.c.cnt + 2) // 2,
    )
    yearly = (
        select(
            priced.c.neighborhood,
            priced.c.year,
            func.avg(case((is_median_row, priced.c.price))).label("median_price"),
            func.count().label("cnt"),
        )
        .group_by(priced.c.neighborhood, priced.c.year)
        .having(func.count() >= min_transactions)
        .subquery()
    )
    prev = yearly.alias("prev")
    curr = yearly.alias("curr")
    yoy_expr = ((curr.c.median_price - prev.c.median_price) / prev.c.median_price * 100).label("yoy_change_pct")
    query = (
        select(
            curr.c.neighborhood,
            curr.c.year,
            curr.c.median_price,
            yoy_expr,
        )
        .outerjoin(
            prev,
            (curr.c.neighborhood == prev.c.neighborhood)
            & (curr.c.year == prev.c.year + 1),
        )
        .order_by(curr.c.neighborhood, curr.c.year)
    )
    if neighborhood:
        query = query.where(curr.c.neighborhood == neighborhood)

    result = await session.exec(query)
    return result.mappings().all()


@app.get("/analytics/stale-parcels", response_model=list[StaleParcel])
async def get_stale_parcels(
    min_years: float = Query(10.0, description="Minimum years since last sale"),
    parcel_class: ParcelClass | None = None,
    limit: int = Query(50, le=500),
    session: AsyncSession = Depends(get_session),
):
    """Find parcels that haven't changed hands recently."""
    years_expr = days_between(func.current_date(), func.max(Transaction.sale_date)) / 365.25
    query = (
        select(
            Transaction.parcel_id,
            # Aggregated so Postgres accepts the GROUP BY (one row per parcel);
            # a parcel's location/class are consistent across its transactions.
            func.max(Transaction.parcel_location).label("parcel_location"),
            func.max(Transaction.parcel_class).label("parcel_class"),
            func.max(Transaction.sale_date).label("last_sale_date"),
            func.max(Transaction.sale_price).label("last_sale_price"),
            years_expr.label("years_since_sale"),
        )
        .group_by(Transaction.parcel_id)
        .having(years_expr >= min_years)
        .order_by(desc(years_expr))
        .limit(limit)
    )
    if parcel_class:
        query = query.where(Transaction.parcel_class == parcel_class)

    result = await session.exec(query)
    return result.mappings().all()


@app.get("/analytics/acquisition-waves", response_model=list[AcquisitionWave])
async def get_acquisition_waves(
    window_days: int = Query(90, description="Rolling window size in days"),
    min_acquisitions: int = Query(5, description="Minimum purchases within the window"),
    sale_date__gte: date | None = None,
    sale_date__lte: date | None = None,
    limit: int = Query(50, le=500),
    session: AsyncSession = Depends(get_session),
):
    """Find owners who made many purchases in a short window — bulk acquisitions."""
    # Window starts must be DISTINCT (owner, date) pairs. Joining the raw
    # table against itself multiplied the counts quadratically for owners
    # with many same-day purchases (630 same-day buys => ~397k pairs).
    starts = select(
        Transaction.new_owner.label("owner"),
        Transaction.sale_date.label("start_date"),
    ).distinct()
    if sale_date__gte:
        starts = starts.where(Transaction.sale_date >= sale_date__gte)
    if sale_date__lte:
        starts = starts.where(Transaction.sale_date <= sale_date__lte)
    starts = starts.subquery()

    # Aggregate purchases to deals first: a portfolio purchase stamps the
    # whole deal price on every parcel row, so summing raw rows counted a
    # $10M deal hundreds of times. One (owner, date, price) group = one deal
    # of parcel_count parcels.
    deals = (
        select(
            Transaction.new_owner.label("owner"),
            Transaction.sale_date.label("deal_date"),
            Transaction.sale_price.label("deal_price"),
            func.count().label("parcel_count"),
        )
        .group_by(Transaction.new_owner, Transaction.sale_date, Transaction.sale_price)
        .subquery()
    )

    window_end_expr = date_add_days(starts.c.start_date, window_days)
    count_expr = func.sum(deals.c.parcel_count).label("acquisition_count")
    spent_expr = func.sum(deals.c.deal_price).label("total_spent")

    windows = (
        select(
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
    ranked = select(
        windows,
        func.row_number()
        .over(
            partition_by=windows.c.owner_name,
            order_by=[desc(windows.c.acquisition_count), windows.c.window_start],
        )
        .label("rn"),
    ).subquery()
    query = (
        select(
            ranked.c.owner_name,
            ranked.c.window_start,
            ranked.c.window_end,
            ranked.c.acquisition_count,
            ranked.c.total_spent,
        )
        .where(ranked.c.rn == 1)
        .order_by(desc(ranked.c.acquisition_count))
        .limit(limit)
    )

    result = await session.exec(query)
    return result.mappings().all()


@app.get("/analytics/owner-search")
async def search_owners(
    q: str = Query(..., min_length=2, description="Partial owner name to search"),
    limit: int = Query(10, le=50),
    session: AsyncSession = Depends(get_session),
) -> list[str]:
    """Return distinct owner names matching the query string."""
    query = (
        select(Transaction.new_owner)
        .where(Transaction.new_owner.ilike(f"%{q}%"))
        .distinct()
        .order_by(Transaction.new_owner)
        .limit(limit)
    )
    result = await session.exec(query)
    return result.all()


# Mailing addresses shared by more owners than this are service addresses
# (title companies, registered agents), not evidence of common ownership.
_MAX_OWNERS_PER_ADDRESS = 12


@app.get("/analytics/owner-profile", response_model=OwnerProfile)
async def get_owner_profile(
    owner_name: str = Query(..., description="Exact owner name"),
    session: AsyncSession = Depends(get_session),
):
    """Activity history and related entities for one owner.

    Aggregated in Python: even the county's biggest investors have a few
    thousand transactions, and the deal grouping / buy-sell pairing logic
    is much clearer here than in portable SQL.
    """
    buys = (
        await session.exec(
            select(Transaction.parcel_id, Transaction.sale_date, Transaction.sale_price)
            .where(Transaction.new_owner == owner_name)
        )
    ).all()
    sells = (
        await session.exec(
            select(Transaction.parcel_id, Transaction.sale_date, Transaction.sale_price)
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

    for role, rows, count_key, money_key in (
        ("buy", buys, "buy_count", "total_spent"),
        ("sell", sells, "sell_count", "total_received"),
    ):
        seen_deals: set[tuple] = set()
        for parcel_id, sale_date, price in rows:
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
    addr_rows = (
        await session.exec(
            select(Transaction.mailing_address)
            .where(Transaction.new_owner == owner_name)
            .where(Transaction.mailing_address != "")
            .distinct()
        )
    ).all()
    related: list[RelatedOwner] = []
    if addr_rows:
        rows = (
            await session.exec(
                select(
                    Transaction.new_owner,
                    Transaction.mailing_address,
                    func.count().label("cnt"),
                )
                .where(Transaction.mailing_address.in_(addr_rows))
                .where(Transaction.new_owner != owner_name)
                .group_by(Transaction.new_owner, Transaction.mailing_address)
                .order_by(desc("cnt"))
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


@app.get("/parcels/{parcel_id}/comps", response_model=ParcelComps)
async def get_parcel_comps(
    parcel_id: str,
    months: int = Query(18, description="How far back to look for comparable sales"),
    limit: int = Query(10, le=50),
    session: AsyncSession = Depends(get_session),
):
    """Recent arm's-length sales in the same neighborhood and class."""
    latest = (
        await session.exec(
            select(Transaction.neighborhood, Transaction.parcel_class)
            .where(Transaction.parcel_id == parcel_id)
            .order_by(desc(Transaction.sale_date))
            .limit(1)
        )
    ).first()
    if latest is None or latest[0] is None:
        return ParcelComps(
            neighborhood=None,
            parcel_class=latest[1] if latest else None,
            median_price=None,
            comps=[],
        )
    neighborhood, parcel_class = latest

    cutoff = date.today() - timedelta(days=months * 30)
    rows = (
        await session.exec(
            select(
                Transaction.parcel_id,
                Transaction.parcel_location,
                Transaction.sale_date,
                Transaction.sale_price,
                Transaction.acres,
            )
            .where(Transaction.neighborhood == neighborhood)
            .where(Transaction.parcel_class == parcel_class)
            .where(Transaction.parcel_id != parcel_id)
            .where(Transaction.sale_date >= cutoff)
            .where(market_sale_criteria())
            .order_by(desc(Transaction.sale_date))
            .limit(limit)
        )
    ).all()

    prices = sorted(r[3] for r in rows)
    median = None
    if prices:
        mid = len(prices) // 2
        median = prices[mid] if len(prices) % 2 else (prices[mid - 1] + prices[mid]) / 2

    return ParcelComps(
        neighborhood=neighborhood,
        parcel_class=parcel_class,
        median_price=median,
        comps=[
            CompSale(
                parcel_id=r[0], parcel_location=r[1], sale_date=r[2],
                sale_price=r[3], acres=r[4] or 0.0,
            )
            for r in rows
        ],
    )


@app.get("/health/data", response_model=DataHealth)
async def get_data_health(session: AsyncSession = Depends(get_session)):
    """Freshness and coverage stats for the self-populating pipeline."""
    total_txns = (await session.exec(select(func.count()).select_from(Transaction))).one()
    total_parcels = (await session.exec(select(func.count()).select_from(Parcel))).one()
    latest_sale = (await session.exec(select(func.max(Transaction.sale_date)))).one()
    last_ingest = (await session.exec(select(func.max(DataFile.ingested_at)))).one()
    geocoded = (
        await session.exec(
            select(func.count())
            .select_from(Parcel)
            .where(Parcel.latitude.is_not(None))
            .where(Parcel.latitude != 0.0)
        )
    ).one()
    market_sales = (
        await session.exec(
            select(func.count()).select_from(Transaction).where(market_sale_criteria())
        )
    ).one()
    return DataHealth(
        total_transactions=total_txns,
        total_parcels=total_parcels,
        latest_sale_date=latest_sale,
        last_ingest_at=last_ingest,
        geocoded_pct=(geocoded / total_parcels * 100) if total_parcels else 0.0,
        market_sale_pct=(market_sales / total_txns * 100) if total_txns else 0.0,
    )


@app.get("/analytics/owner-holdings", response_model=list[OwnerParcel])
async def get_owner_holdings(
    owner_name: str = Query(..., description="Exact owner name"),
    session: AsyncSession = Depends(get_session),
):
    """Return all parcels currently owned by an entity (most recent transaction per parcel)."""
    ranked = (
        select(
            Transaction.parcel_id,
            Transaction.parcel_location,
            Transaction.parcel_class,
            Transaction.acres,
            Transaction.sale_date.label("last_sale_date"),
            Transaction.sale_price.label("last_sale_price"),
            Transaction.assessed_total,
            Transaction.new_owner,
            func.row_number()
            .over(partition_by=Transaction.parcel_id, order_by=desc(Transaction.sale_date))
            .label("rn"),
        )
        .subquery()
    )
    query = (
        select(
            ranked.c.parcel_id,
            ranked.c.parcel_location,
            ranked.c.parcel_class,
            ranked.c.acres,
            ranked.c.last_sale_date,
            ranked.c.last_sale_price,
            func.coalesce(ranked.c.assessed_total, 0).label("assessed_total"),
            Parcel.latitude,
            Parcel.longitude,
        )
        .join(Parcel, ranked.c.parcel_id == Parcel.parcel_id, isouter=True)
        .where(ranked.c.rn == 1)
        .where(ranked.c.new_owner == owner_name)
        .order_by(ranked.c.last_sale_date.desc())
    )
    result = await session.exec(query)
    rows = result.mappings().all()

    # Holdings acquired on the same date for the same recorded price came in
    # one conveyance; the county stamps the full deal price on each parcel.
    deal_counts: dict[tuple, int] = {}
    for row in rows:
        key = (row["last_sale_date"], row["last_sale_price"])
        deal_counts[key] = deal_counts.get(key, 0) + 1

    return [
        OwnerParcel(
            parcel_id=row["parcel_id"],
            parcel_location=row["parcel_location"],
            parcel_class=row["parcel_class"],
            acres=row["acres"] or 0.0,
            last_sale_date=row["last_sale_date"],
            last_sale_price=row["last_sale_price"] or 0.0,
            assessed_total=row["assessed_total"],
            latitude=row["latitude"],
            longitude=row["longitude"],
            deal_size=deal_counts[(row["last_sale_date"], row["last_sale_price"])],
        )
        for row in rows
    ]








