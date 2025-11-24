
from enum import Enum
from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Path, Query
from pydantic import BaseModel, Field
from sqlmodel import Field, Session, and_, select, desc
from sqlmodel.ext.asyncio.session import AsyncSession
# from fastapi_filters import create_filters, create_filters_from_model, FilterValues
# from fastapi_filters.ext.sqlalchemy import apply_filters
from sqlalchemy import func
from sqlalchemy.orm import selectinload

from fastapi_filter import FilterDepends, with_prefix
from fastapi_filter.contrib.sqlalchemy import Filter

from db.engine import engine, get_session, init_db
from db.models import OwnerStats, Transaction, DataFile, TransactionListModel, Parcel, ParcelListModel, ParcelClass
from db.ingestors import ingest_data_files
from services.data_retrieval import retrieve_yearly_data

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Server is starting...")
    init_db()
    yield
    print("Server is stopping")

app = FastAPI(
    title="Nate's Real Estate API",
    description="This is a simple api for learning",
    version="0.1.0",
    lifespan=lifespan
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
        # Join Parcel and ensure lat/lon are not null
        statement = statement.join(Parcel, Transaction.parcel_id == Parcel.parcel_id).where(
            and_(
                Parcel.latitude.is_not(None),
                Parcel.longitude.is_not(None)
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

@app.get("/parcels/{parcel_id}/history", response_model=list[Transaction])
async def get_parcel_history(parcel_id: str, session: AsyncSession = Depends(get_session)):
    """View the full sales history of a specific parcel to spot 'Flips'."""
    query = select(Transaction).where(Transaction.parcel_id == parcel_id).order_by(Transaction.sale_date.desc())
    result = await session.exec(query)
    return result.all()










