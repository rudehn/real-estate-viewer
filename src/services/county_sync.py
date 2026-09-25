"""Download-and-ingest for the county's non-sales datasets.

A dataset's newest file is ingested once (tracked by DataFile.filename, since
these files never change once published). Older downloads are deleted to keep
the data volume small; CAMA alone is 125 MB a month.
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Awaitable, Callable
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from county import sources
from db.models import DataFile
from logging_config import get_logger

logger = get_logger(__name__)

Ingest = Callable[[Path, AsyncEngine], Awaitable[object]]


def _file_date(dataset: str, filename: str) -> dt.date:
    match = sources.DATASETS[dataset].pattern.search(filename)
    return dt.datetime.strptime(match.group(1), "%Y%m%d").date()


async def _ingested_names(engine: AsyncEngine, dataset: str) -> list[str]:
    pattern = sources.DATASETS[dataset].pattern
    async with AsyncSession(engine) as s:
        names = (await s.exec(select(DataFile.filename))).all()
    return [n for n in names if pattern.fullmatch(n)]


async def sync_dataset(
    dataset: str,
    ingest: Ingest,
    *,
    data_dir: Path,
    engine: AsyncEngine | None = None,
    client=None,
    min_age_days: int = 0,
) -> bool:
    if engine is None:
        from db.engine import engine as default_engine

        engine = default_engine
    own_client = client is None
    client = client or sources.county_client()
    try:
        files = await sources.list_files(dataset, client)
        if not files:
            logger.warning("No %s files listed on the county site.", dataset)
            return False
        newest = files[-1]
        done = await _ingested_names(engine, dataset)
        if newest in done:
            return False
        if min_age_days and done:
            last = max(_file_date(dataset, n) for n in done)
            if (_file_date(dataset, newest) - last).days < min_age_days:
                return False
        path = await sources.download(dataset, newest, data_dir, client)
    finally:
        if own_client:
            await client.aclose()

    logger.info("Ingesting %s...", path.name)
    await ingest(path, engine)
    async with AsyncSession(engine) as s:
        s.add(DataFile(filename=newest, ingested_at=dt.datetime.now()))
        await s.commit()
    for old in path.parent.iterdir():
        if old != path and sources.DATASETS[dataset].pattern.fullmatch(old.name):
            old.unlink(missing_ok=True)
    return True
