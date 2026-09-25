"""In-process cache for aggregate responses, keyed by data_version.

A new ingest bumps data_version, so stale entries are never served; they
simply age out of the LRU.
"""
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

import sqlalchemy as sa

from db.county_models import DataVersion


class VersionedCache:
    def __init__(self, maxsize: int = 1024):
        self.maxsize = maxsize
        self._data: OrderedDict[tuple, Any] = OrderedDict()

    async def get_or_compute(
        self, key: tuple, version: int, compute: Callable[[], Awaitable[Any]]
    ) -> Any:
        full_key = (version, *key)
        if full_key in self._data:
            self._data.move_to_end(full_key)
            return self._data[full_key]
        value = await compute()
        self._data[full_key] = value
        while len(self._data) > self.maxsize:
            self._data.popitem(last=False)
        return value

    def clear(self) -> None:
        self._data.clear()


cache = VersionedCache()


async def data_version(session) -> int:
    t = DataVersion.__table__
    result = await session.execute(sa.select(t.c.version).where(t.c.id == 1))
    return result.scalar_one_or_none() or 0
