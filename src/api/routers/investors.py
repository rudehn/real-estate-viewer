from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from api.filters import Filters, get_filters, honored
from db.engine import get_session
from db.models import AcquisitionWave, NetSellerStats, OwnerStats, ParcelClass
from services.analytics.owners import absentee_owners, acquisition_waves, net_sellers

router = APIRouter(prefix="/investors", tags=["investors"])


class Waves(BaseModel):
    applied_filters: list[str]
    rows: list[AcquisitionWave]


class NetSellers(BaseModel):
    applied_filters: list[str]
    rows: list[NetSellerStats]


class Absentee(BaseModel):
    applied_filters: list[str]
    rows: list[OwnerStats]


@router.get("/acquisition-waves", response_model=Waves)
async def waves(f: Filters = Depends(get_filters), window_days: int = Query(90, ge=7, le=730),
                min_acquisitions: int = Query(5, ge=2), limit: int = Query(50, ge=1, le=500),
                session: AsyncSession = Depends(get_session)):
    rows = await acquisition_waves(session, window_days=window_days,
                                   min_acquisitions=min_acquisitions, date_from=f.date_from,
                                   date_to=f.date_to, limit=limit)
    return Waves(applied_filters=honored(f, ["date_from", "date_to"]), rows=rows)


@router.get("/net-sellers", response_model=NetSellers)
async def sellers(f: Filters = Depends(get_filters), min_net_sells: int = Query(3, ge=1),
                  limit: int = Query(50, ge=1, le=500),
                  session: AsyncSession = Depends(get_session)):
    rows = await net_sellers(session, min_net_sells=min_net_sells, date_from=f.date_from,
                             date_to=f.date_to, limit=limit)
    return NetSellers(applied_filters=honored(f, ["date_from", "date_to"]), rows=rows)


@router.get("/absentee-owners", response_model=Absentee)
async def absentee(f: Filters = Depends(get_filters), limit: int = Query(50, ge=1, le=500),
                   session: AsyncSession = Depends(get_session)):
    single = f.classes[0] if f.classes and len(f.classes) == 1 else None
    rows = await absentee_owners(session, parcel_class=ParcelClass[single] if single else None,
                                 limit=limit)
    return Absentee(applied_filters=["classes"] if single else [], rows=rows)
