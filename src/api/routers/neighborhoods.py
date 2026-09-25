from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from api.cache import cache, data_version
from api.filters import Filters, get_filters
from db.engine import get_session
from services.analytics.neighborhoods import (
    NeighborhoodReport,
    NeighborhoodRow,
    TrendRow,
    list_neighborhoods,
    neighborhood_report,
    neighborhood_trends,
)

router = APIRouter(prefix="/neighborhoods", tags=["neighborhoods"])


class NeighborhoodList(BaseModel):
    applied_filters: list[str]
    rows: list[NeighborhoodRow]


class TrendList(BaseModel):
    applied_filters: list[str]
    rows: list[TrendRow]


@router.get("", response_model=NeighborhoodList)
async def neighborhoods(f: Filters = Depends(get_filters),
                        session: AsyncSession = Depends(get_session)):
    version = await data_version(session)
    rows = await cache.get_or_compute(("neighborhoods", f.model_dump_json()), version,
                                      lambda: list_neighborhoods(session, f))
    return NeighborhoodList(applied_filters=f.active(), rows=rows)


@router.get("/trends", response_model=TrendList)
async def trends(f: Filters = Depends(get_filters),
                 codes: list[str] | None = Query(None),
                 limit: int = Query(10, ge=1, le=50),
                 min_sales: int = Query(5, ge=1),
                 session: AsyncSession = Depends(get_session)):
    rows = await neighborhood_trends(session, f, codes, limit, min_sales)
    return TrendList(applied_filters=f.active(), rows=rows)


@router.get("/{code}", response_model=NeighborhoodReport)
async def report(code: str, session: AsyncSession = Depends(get_session)):
    return await neighborhood_report(session, code)
