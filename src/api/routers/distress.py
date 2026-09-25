from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from api.filters import Filters, get_filters, honored
from db.engine import get_session
from db.models import DistressedSale, ParcelClass, StaleParcel
from services.analytics.distress import distressed_sales, stale_parcels

router = APIRouter(prefix="/distress", tags=["distress"])


class DistressedList(BaseModel):
    applied_filters: list[str]
    rows: list[DistressedSale]


class StaleList(BaseModel):
    applied_filters: list[str]
    rows: list[StaleParcel]


def _classes(f: Filters) -> list[ParcelClass] | None:
    return [ParcelClass[c] for c in f.classes] if f.classes else None


@router.get("/distressed-sales", response_model=DistressedList)
async def distressed(f: Filters = Depends(get_filters),
                     max_ratio: float = Query(0.7, gt=0, le=1),
                     limit: int = Query(50, ge=1, le=500),
                     session: AsyncSession = Depends(get_session)):
    rows = await distressed_sales(session, max_ratio=max_ratio, date_from=f.date_from,
                                  date_to=f.date_to, classes=_classes(f), limit=limit)
    return DistressedList(applied_filters=honored(f, ["date_from", "date_to", "classes"]),
                          rows=rows)


@router.get("/stale-parcels", response_model=StaleList)
async def stale(f: Filters = Depends(get_filters),
                min_years: float = Query(10.0, ge=1),
                limit: int = Query(50, ge=1, le=500),
                session: AsyncSession = Depends(get_session)):
    rows = await stale_parcels(session, min_years=min_years, classes=_classes(f), limit=limit)
    return StaleList(applied_filters=honored(f, ["classes"]), rows=rows)
