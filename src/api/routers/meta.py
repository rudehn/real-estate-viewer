import datetime as dt

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from api.cache import cache, cached_latest_sale_date, data_version
from county.sources import DATASETS
from db.county_models import DataVersion, ParcelSummary
from db.engine import get_session
from db.models import DataFile

router = APIRouter(tags=["meta"])

# name, label, DataFile pattern, days until stale (None = never flagged)
# Patterns come from county.sources.DATASETS so a differently-cased file name
# (the county's naming is not consistent) is recognized the same way the
# ingest scraper recognizes it, instead of drifting out of sync.
_SOURCES = (
    ("cama", "County appraisal (CAMA)", DATASETS["cama"].pattern, 45),
    ("taxroll", "Tax roll", DATASETS["taxroll"].pattern, 21),
    ("neighborhoods", "Neighborhood names", DATASETS["neighborhoods"].pattern, None),
)
SALES_STALE_DAYS = 14


class SourceStatus(BaseModel):
    name: str
    label: str
    file: str | None
    ingested_at: dt.datetime | None
    as_of: dt.date | None
    stale: bool


class Meta(BaseModel):
    data_version: int
    updated_at: dt.datetime | None
    latest_sale_date: dt.date | None
    parcel_count: int
    mapped_parcel_count: int
    sources: list[SourceStatus]
    ranges: dict[str, list[float]]


def _percentile(sorted_values: list[float], p: float) -> float:
    return sorted_values[min(len(sorted_values) - 1, int(len(sorted_values) * p))]


async def _ranges(session: AsyncSession) -> dict[str, list[float]]:
    s = ParcelSummary.__table__
    out = {}
    for name, column in (("price", s.c.last_sale_price), ("living_sqft", s.c.living_sqft),
                         ("year_built", s.c.year_built)):
        values = sorted(
            v for (v,) in (await session.exec(
                sa.select(column).where(column.isnot(None), column > 0)
            )).all()
        )
        out[name] = [_percentile(values, 0.01), _percentile(values, 0.99)] if values else [0, 0]
    return out


@router.get("/meta", response_model=Meta)
async def meta(session: AsyncSession = Depends(get_session)) -> Meta:
    version = await data_version(session)
    today = dt.date.today()
    latest = await cached_latest_sale_date(session)
    s = ParcelSummary.__table__
    parcel_count = (await session.exec(sa.select(sa.func.count()).select_from(s))).scalar_one()
    mapped = (await session.exec(
        sa.select(sa.func.count()).select_from(s)
        .where(s.c.is_active.is_(True), s.c.latitude.isnot(None))
    )).scalar_one()
    files = (await session.exec(sa.select(DataFile.filename, DataFile.ingested_at))).all()
    sources = [SourceStatus(
        name="sales", label="Sales", file=None, ingested_at=None, as_of=latest,
        stale=latest is None or (today - latest).days > SALES_STALE_DAYS,
    )]
    for name, label, pattern, stale_days in _SOURCES:
        matches = sorted(
            ((m.group(1), f, at) for f, at in files if (m := pattern.fullmatch(f))),
        )
        if matches:
            stamp, file, at = matches[-1]
            as_of = dt.datetime.strptime(stamp, "%Y%m%d").date()
        else:
            file, at, as_of = None, None, None
        stale = stale_days is not None and (as_of is None or (today - as_of).days > stale_days)
        sources.append(SourceStatus(name=name, label=label, file=file, ingested_at=at,
                                    as_of=as_of, stale=stale))
    updated = (await session.exec(
        sa.select(DataVersion.updated_at).where(DataVersion.id == 1)
    )).scalar_one_or_none()
    ranges = await cache.get_or_compute(("ranges",), version, lambda: _ranges(session))
    return Meta(data_version=version, updated_at=updated, latest_sale_date=latest,
                parcel_count=parcel_count, mapped_parcel_count=mapped, sources=sources,
                ranges=ranges)
