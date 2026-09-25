from fastapi import APIRouter, Depends, Query
from sqlmodel.ext.asyncio.session import AsyncSession

from db.engine import get_session
from services.analytics.comps import CompsResult, get_comps
from services.analytics.parcels import ParcelProfile, TimelineEvent, get_profile, get_timeline

router = APIRouter(prefix="/parcels", tags=["parcels"])


@router.get("/{parcel_id}", response_model=ParcelProfile)
async def profile(parcel_id: str, session: AsyncSession = Depends(get_session)):
    return await get_profile(session, parcel_id)


@router.get("/{parcel_id}/timeline", response_model=list[TimelineEvent])
async def timeline(parcel_id: str, session: AsyncSession = Depends(get_session)):
    return await get_timeline(session, parcel_id)


@router.get("/{parcel_id}/comps", response_model=CompsResult)
async def comps(parcel_id: str, limit: int = Query(10, ge=1, le=50),
                session: AsyncSession = Depends(get_session)):
    return await get_comps(session, parcel_id, limit)
