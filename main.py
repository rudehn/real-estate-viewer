
from enum import Enum
from contextlib import contextmanager

from fastapi import Depends, FastAPI, HTTPException, Path, Query
from pydantic import BaseModel, Field
from sqlmodel import Field, Session, select
from sqlmodel.ext.asyncio.session import AsyncSession
# from fastapi_filters import create_filters, create_filters_from_model, FilterValues
# from fastapi_filters.ext.sqlalchemy import apply_filters
from sqlalchemy import func

from fastapi_filter import FilterDepends, with_prefix
from fastapi_filter.contrib.sqlalchemy import Filter

from db.engine import engine, get_session, initdb
from db.models import Transaction, DataFile, TransactionListModel, Parcel, ParcelListModel, ParcelClass
from db.ingestors import ingest_data_files
from services.data_retrieval import retrieve_yearly_data

@contextmanager
def lifespan(app: FastAPI):
    print("Server is starting...")
    initdb()
    ingest_data_files("data")
    # ingest_yearly_files("data/yearly/SALES_2025/")
    # ingest_yearly_file("data/yearly/SALES_2025/SALES_2025_AGR.csv")
    yield
    print("Server is stopping")

app = FastAPI(
    title="Nate's Simple API",
    description="This is a simple api for learning",
    version="0.1.0",
    # lifespan=lifespan
)


initdb()
# retrieve_yearly_data()
ingest_data_files("data")
# initdb()
# ingest_yearly_file("data/yearly/SALES_2025/SALES_2025_AGR.csv")


# https://go.mcohio.org/applications/treasurer/search/data/Yearly/SALES_2025.zip
# https://go.mcohio.org/applications/treasurer/search/fdpopup.cfm?dtype=YS

# https://testdriven.io/blog/fastapi-sqlmodel/
# https://github.com/arthurio/fastapi-filter/blob/main/examples/fastapi_filter_sqlalchemy.py

class TransactionFilter(Filter):
    acres: int | None = None
    # acres_gte: int | None = Field(Query(default=None, description="this is nice"))
    new_owner__ilike: str | None = None
    new_owner__like: str | None = None
    class Constants(Filter.Constants):
        model = Transaction 
        # search_model_fields = ["name"]

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
def get_parcels(offset: int = 0, limit: int = 50,
                     filters: ParcelFilter = FilterDepends(ParcelFilter),
                     session: Session = Depends(get_session)):
    query = select(Parcel).offset(offset).limit(limit)
    query = filters.filter(query)
    parcels = session.exec(query).all()

    count = session.exec(filters.filter(select(func.count()).select_from(Parcel))).one()
    # count = session.exec(select(func.count()).select_from(Parcel)).one()

    # query_stmt = apply_filters(select(RealEstateTransaction).offset(offset).limit(limit), filters)
    # transactions = session.exec(query_stmt).all()
    # count_stmt = apply_filters(select(func.count()).select_from(RealEstateTransaction), filters)
    # count = session.exec(count_stmt).one()
    return ParcelListModel(count=count, entities=parcels)

# @app.get("/transactions", response_model=list[RealEstateTransaction])
@app.get("/transactions", response_model=TransactionListModel)
def get_transactions(offset: int = 0, limit: int = 50,
                     filters: TransactionFilter = FilterDepends(TransactionFilter),
                     session: Session = Depends(get_session)):
    query = select(Transaction).offset(offset).limit(limit)
    query = filters.filter(query)
    transactions = session.exec(query).all()

    count = session.exec(filters.filter(select(func.count()).select_from(Transaction))).one()

    # query_stmt = apply_filters(select(RealEstateTransaction).offset(offset).limit(limit), filters)
    # transactions = session.exec(query_stmt).all()
    # count_stmt = apply_filters(select(func.count()).select_from(RealEstateTransaction), filters)
    # count = session.exec(count_stmt).one()
    return TransactionListModel(count=count, entities=transactions)

@app.get("/transactions/{transaction_id}", response_model=Transaction)
def get_transaction(transaction_id: int, session: Session = Depends(get_session)):
    transaction = session.get(Transaction, transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Not Found")
    return transaction




















# class Category(Enum):
#     """Category of an item"""
#     TOOLS = "tools"
#     CONSUMABLES = "consumables"

# class Item(BaseModel):
#     """Representation of an item"""
#     name: str = Field(description="Name of the item.")
#     price: float = Field(description="Price of the item in Euro.")
#     count: int = Field(description="Amount of instances in stock")
#     id: int = Field(description="Unique identifier for this item")
#     category: Category = Field(description="Category this item belongs to")


# items = {
#     0: Item(name="Hammer", price=9.99, count=20, id=0, category=Category.TOOLS),
#     1: Item(name="Pliers", price=5.99, count=20, id=1, category=Category.TOOLS),
#     2: Item(name="Nails", price=1.99, count=100, id=2, category=Category.CONSUMABLES),
    
# }


# @app.get(
#     "/items/{item_id}",
#     responses={
#         404: {"description": "Item not found"},
#     })
# def get_item(item_id: int) -> Item:
#     if item_id not in items:
#         raise HTTPException(status_code=404, detail="Not Found")
#     return items[item_id]


# Selection = dict[str, str | int | float | Category | None]
# @app.get("/items/")
# def get_items(name: str | None = None,
#               price: float | None = None,
#               count: int | None = None,
#               category: Category | None = None) -> dict[str, Selection | list[Item]]:
#     print("in endpoint")
#     def check_item(item: Item) -> bool:
#         return all (
#             (
#                 name is None or item.name == name,
#                 price is None or item.price == price,
#                 count is None or item.count == count,
#                 category is None or item.category is category,
#             )
#         )
#     selection = [item for item in items.values() if check_item(item)]
#     return {
#         "query": {"name": name, "price": price, "count": count, "category": category},
#         "selection": selection,
#     }

# @app.post("/items")
# def add_item(item: Item) -> dict[str, Item]:
#     if item.id in items:
#         HTTPException(status_code=400, detail=f"Item with {item.id=} already exists.")
    
#     items[item.id] = item
#     return {"added": item}

# @app.put('/items/{item_id}')
# def put_item(item_id: int = Path(ge=0),
#              name: str | None = Query(default=None, min_length=1, max_length=8),
#              price: float | None = Query(default=None, gt=0.0),
#              count: int | None = Query(default=None, ge=0)) -> dict[str, Item]:
#     if item_id not in items:
#         HTTPException(status_code=404, detail="Not Found")
#     if all(info is None for info in (name, price, count)):
#         raise HTTPException(
#             status_code=400, detail="No parameters provided"
#         )
#     item = items[item_id]
#     if name is not None:
#         item.name = name
#     if price is not None:
#         item.price = price
#     if count is not None:
#         item.count = count

#     return {"updated": item}

# @app.delete("/items/{item_id}")
# def delete_item(item_id: int):
#     if item_id not in items:
#         HTTPException(status_code=404, detail="Not Found")
    
#     item = items.pop(item_id)
#     return {"deleted": item}