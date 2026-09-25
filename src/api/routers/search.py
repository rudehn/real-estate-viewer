from fastapi import APIRouter, Depends, Query
from sqlmodel.ext.asyncio.session import AsyncSession

from db.engine import get_session
from services.analytics.search import SearchResults, search

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResults)
async def search_everything(
    q: str = Query("", max_length=200),
    limit: int = Query(8, ge=1, le=25),
    session: AsyncSession = Depends(get_session),
) -> SearchResults:
    return await search(session, q, limit)
