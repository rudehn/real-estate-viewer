from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from api.filters import Filters, get_filters, honored
from db.engine import get_session
from db.models import ParcelClass
from services.analytics.sales import (
    FlipsPage,
    SalesPage,
    find_flips,
    list_sales,
    stream_sales_csv,
)

router = APIRouter(prefix="/sales", tags=["sales"])
Sort = Literal["sale_date", "sale_price", "price_per_sqft", "living_sqft"]
Order = Literal["desc", "asc"]


@router.get("", response_model=SalesPage)
async def sales(
    f: Filters = Depends(get_filters),
    sort: Sort = "sale_date",
    order: Order = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    market_only: bool = False,
    session: AsyncSession = Depends(get_session),
):
    return await list_sales(session, f, sort=sort, order=order, page=page,
                            page_size=page_size, market_only=market_only)


@router.get(".csv")
async def sales_csv(
    f: Filters = Depends(get_filters),
    sort: Sort = "sale_date",
    order: Order = "desc",
    market_only: bool = False,
    session: AsyncSession = Depends(get_session),
):
    return StreamingResponse(
        stream_sales_csv(session, f, sort=sort, order=order, market_only=market_only),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="sales.csv"'},
    )


@router.get("/flips", response_model=FlipsPage)
async def flips(
    f: Filters = Depends(get_filters),
    max_hold_days: int = Query(730, ge=1, le=3650),
    min_profit_pct: float = Query(0.1, ge=0),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
):
    rows = await find_flips(
        session, max_hold_days=max_hold_days, min_profit_pct=min_profit_pct,
        date_from=f.date_from, date_to=f.date_to,
        classes=[ParcelClass[c] for c in f.classes] if f.classes else None, limit=limit,
    )
    return FlipsPage(applied_filters=honored(f, ["date_from", "date_to", "classes"]), rows=rows)
