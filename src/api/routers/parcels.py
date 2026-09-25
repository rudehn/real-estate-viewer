from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from db.engine import get_session
from services.analytics.parcels import ParcelProfile, TimelineEvent, get_profile, get_timeline

router = APIRouter(prefix="/parcels", tags=["parcels"])


@router.get("/{parcel_id}", response_model=ParcelProfile)
async def profile(parcel_id: str, session: AsyncSession = Depends(get_session)):
    return await get_profile(session, parcel_id)


@router.get("/{parcel_id}/timeline", response_model=list[TimelineEvent])
async def timeline(parcel_id: str, session: AsyncSession = Depends(get_session)):
    return await get_timeline(session, parcel_id)
