
import asyncio
import os
from enum import Enum
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path as FilePath

from fastapi import Depends, FastAPI, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlmodel import Field, Session, and_, select, desc
from sqlmodel.ext.asyncio.session import AsyncSession
# from fastapi_filters import create_filters, create_filters_from_model, FilterValues
# from fastapi_filters.ext.sqlalchemy import apply_filters
from sqlalchemy import func, Integer
from sqlalchemy.orm import selectinload

from fastapi_filter import FilterDepends, with_prefix
from fastapi_filter.contrib.sqlalchemy import Filter

from db.engine import engine, get_session, init_db
from db.models import (
    OwnerStats, NeighborhoodStats, Transaction, DataFile, TransactionListModel,
    Parcel, ParcelListModel, ParcelClass,
    FlipResult, DistressedSale, OwnerHoldings, NetSellerStats,
    NeighborhoodTrend, StaleParcel, AcquisitionWave, OwnerParcel,
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

    # 2. Apply filtering logic from fastapi-filter (for Transaction fields)
    statement = filters.filter(statement)
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


@app.get("/analytics/top-buyers", response_model=list[OwnerStats])
async def get_top_buyers(
    limit: int = 10, 
    min_spent: float = 0,
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
        .limit(limit)
    )

    result = await session.exec(query)
    return result.all()

@app.get("/analytics/top-sellers", response_model=list[OwnerStats])
async def get_top_sellers(limit: int = 10, session: AsyncSession = Depends(get_session)):
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
        .limit(limit)
    )
    result = await session.exec(query)
    return result.all()

@app.get("/analytics/neighborhoods", response_model=list[NeighborhoodStats])
async def get_neighborhood_stats(
    limit: int = Query(50, description="Max neighborhoods to return"),
    min_transactions: int = Query(1, description="Minimum transaction count to include"),
    sale_date__gte: date | None = None,
    sale_date__lte: date | None = None,
    parcel_class: ParcelClass | None = None,
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
    t1 = Transaction.__table__.alias("t1")
    t2 = Transaction.__table__.alias("t2")

    hold_days_expr = func.julianday(t2.c.sale_date) - func.julianday(t1.c.sale_date)
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
        .where(hold_days_expr <= max_hold_days)
        .where(t1.c.sale_price > 0)
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
        .limit(limit)
    )
    if parcel_class:
        query = query.where(ranked.c.parcel_class == parcel_class.value)

    result = await session.exec(query)
    return result.mappings().all()


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
        .limit(limit)
    )
    result = await session.exec(query)
    return result.mappings().all()


@app.get("/analytics/neighborhoods/trends", response_model=list[NeighborhoodTrend])
async def get_neighborhood_trends(
    neighborhood: str | None = Query(None, description="Filter to a single neighborhood code"),
    min_transactions: int = Query(5, description="Min transactions per year to include"),
    session: AsyncSession = Depends(get_session),
):
    """Year-over-year median price change per neighborhood (gentrification score)."""
    year_expr = func.strftime("%Y", Transaction.sale_date).label("year")
    yearly = (
        select(
            Transaction.neighborhood.label("neighborhood"),
            year_expr,
            func.avg(Transaction.sale_price).label("avg_price"),
            func.count().label("cnt"),
        )
        .where(Transaction.neighborhood.is_not(None))
        .where(Transaction.sale_price > 0)
        .group_by(Transaction.neighborhood, year_expr)
        .having(func.count() >= min_transactions)
        .subquery()
    )
    prev = yearly.alias("prev")
    curr = yearly.alias("curr")
    yoy_expr = ((curr.c.avg_price - prev.c.avg_price) / prev.c.avg_price * 100).label("yoy_change_pct")
    query = (
        select(
            curr.c.neighborhood,
            curr.c.year.cast(Integer).label("year"),
            curr.c.avg_price,
            yoy_expr,
        )
        .outerjoin(
            prev,
            (curr.c.neighborhood == prev.c.neighborhood)
            & (curr.c.year.cast(Integer) == prev.c.year.cast(Integer) + 1),
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
    years_expr = (func.julianday("now") - func.julianday(func.max(Transaction.sale_date))) / 365.25
    query = (
        select(
            Transaction.parcel_id,
            Transaction.parcel_location,
            Transaction.parcel_class,
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
    t_outer = Transaction.__table__.alias("t_outer")
    t_inner = Transaction.__table__.alias("t_inner")

    window_end_expr = func.date(t_outer.c.sale_date, f"+{window_days} days")
    count_expr = func.count(t_inner.c.id).label("acquisition_count")
    spent_expr = func.sum(t_inner.c.sale_price).label("total_spent")

    query = (
        select(
            t_outer.c.new_owner.label("owner_name"),
            t_outer.c.sale_date.label("window_start"),
            window_end_expr.label("window_end"),
            count_expr,
            spent_expr,
        )
        .select_from(
            t_outer.join(
                t_inner,
                (t_inner.c.new_owner == t_outer.c.new_owner)
                & (t_inner.c.sale_date >= t_outer.c.sale_date)
                & (t_inner.c.sale_date <= window_end_expr),
            )
        )
        .group_by(t_outer.c.new_owner, t_outer.c.sale_date)
        .having(count_expr >= min_acquisitions)
        .order_by(desc(count_expr))
        .limit(limit)
    )
    if sale_date__gte:
        query = query.where(t_outer.c.sale_date >= sale_date__gte)
    if sale_date__lte:
        query = query.where(t_outer.c.sale_date <= sale_date__lte)

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
        )
        for row in rows
    ]








