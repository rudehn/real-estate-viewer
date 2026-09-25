from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from api.cache import cache, data_version
from api.filters import Filters, get_filters, honored
from db.engine import get_session
from db.models import MarketStatsBucket, OwnerStats
from services.analytics.market import (
    MarketSummary,
    PricePoint,
    market_summary,
    market_trends,
    price_points,
    top_buyers,
    top_sellers,
)

router = APIRouter(prefix="/market", tags=["market"])


class TrendsResponse(BaseModel):
    applied_filters: list[str]
    buckets: list[MarketStatsBucket]


class OwnerRows(BaseModel):
    applied_filters: list[str]
    rows: list[OwnerStats]


class PricePoints(BaseModel):
    applied_filters: list[str]
    total: int
    points: list[PricePoint]


def _key(name: str, f: Filters, *extra) -> tuple:
    return (name, f.model_dump_json(), *extra)


@router.get("/summary", response_model=MarketSummary)
async def summary(f: Filters = Depends(get_filters),
                  session: AsyncSession = Depends(get_session)):
    version = await data_version(session)
    return await cache.get_or_compute(_key("summary", f), version,
                                      lambda: market_summary(session, f))


@router.get("/trends", response_model=TrendsResponse)
async def trends(f: Filters = Depends(get_filters),
                 granularity: Literal["month", "quarter", "year"] = "year",
                 session: AsyncSession = Depends(get_session)):
    version = await data_version(session)
    buckets = await cache.get_or_compute(_key("trends", f, granularity), version,
                                         lambda: market_trends(session, f, granularity))
    return TrendsResponse(applied_filters=f.active(), buckets=buckets)


@router.get("/top-buyers", response_model=OwnerRows)
async def buyers(f: Filters = Depends(get_filters), limit: int = Query(15, ge=1, le=100),
                 session: AsyncSession = Depends(get_session)):
    rows = await top_buyers(session, limit=limit, date_from=f.date_from, date_to=f.date_to)
    return OwnerRows(applied_filters=honored(f, ["date_from", "date_to"]), rows=rows)


@router.get("/top-sellers", response_model=OwnerRows)
async def sellers(f: Filters = Depends(get_filters), limit: int = Query(15, ge=1, le=100),
                  session: AsyncSession = Depends(get_session)):
    rows = await top_sellers(session, limit=limit, date_from=f.date_from, date_to=f.date_to)
    return OwnerRows(applied_filters=honored(f, ["date_from", "date_to"]), rows=rows)


@router.get("/price-points", response_model=PricePoints)
async def points(f: Filters = Depends(get_filters), limit: int = Query(5000, ge=1, le=20000),
                 session: AsyncSession = Depends(get_session)):
    total, pts = await price_points(session, f, limit)
    return PricePoints(applied_filters=f.active(), total=total, points=pts)
