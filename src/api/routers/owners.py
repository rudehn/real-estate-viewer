from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from api.cache import cache, data_version
from api.filters import Filters, get_filters, honored
from db.engine import get_session
from services.analytics.owners import OwnerDetail, OwnerPortfolio, owner_detail, top_owners

router = APIRouter(prefix="/owners", tags=["owners"])
PARCEL_FILTERS = ("date_from", "date_to", "price_min", "price_max", "classes", "beds_min",
                  "sqft_min", "sqft_max", "year_built_min", "year_built_max", "occupancy",
                  "distress_min", "neighborhood")


class OwnerList(BaseModel):
    applied_filters: list[str]
    rows: list[OwnerPortfolio]


@router.get("/top", response_model=OwnerList)
async def top(f: Filters = Depends(get_filters),
              order_by: Literal["parcels", "acres", "value"] = "parcels",
              limit: int = Query(15, ge=1, le=100),
              session: AsyncSession = Depends(get_session)):
    # Aggregates every parcel_summary row, which only changes with data_version.
    version = await data_version(session)
    rows = await cache.get_or_compute(
        ("owners-top", f.model_dump_json(), order_by, limit), version,
        lambda: top_owners(session, f, order_by=order_by, limit=limit),
    )
    return OwnerList(applied_filters=honored(f, PARCEL_FILTERS), rows=rows)


@router.get("/{name}", response_model=OwnerDetail)
async def detail(name: str, session: AsyncSession = Depends(get_session)):
    return await owner_detail(session, name)
