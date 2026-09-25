import pytest
from sqlalchemy import func, select

from db.county_models import Neighborhood
from ingest.bulk import in_thread_chunks, replace_rows

TABLE = Neighborhood.__table__


def rows(n, prefix="N"):
    return ({"code": f"{prefix}{i:05d}", "name": "X", "display_name": "X"} for i in range(n))


async def count(conn):
    return (await conn.execute(select(func.count()).select_from(TABLE))).scalar_one()


async def test_replace_rows_replaces_everything(db_engine):
    async with db_engine.begin() as conn:
        await replace_rows(conn, TABLE, rows(10, "A"))
    async with db_engine.begin() as conn:
        written = await replace_rows(conn, TABLE, rows(2500, "B"))
    async with db_engine.connect() as conn:
        assert written == 2500
        assert await count(conn) == 2500


async def test_failed_ingest_leaves_previous_rows(db_engine):
    async with db_engine.begin() as conn:
        await replace_rows(conn, TABLE, rows(10, "A"))

    def exploding():
        yield from rows(3000, "B")
        raise RuntimeError("layout changed")

    with pytest.raises(RuntimeError):
        async with db_engine.begin() as conn:
            await replace_rows(conn, TABLE, exploding())

    async with db_engine.connect() as conn:
        assert await count(conn) == 10


async def test_in_thread_chunks():
    chunks = [c async for c in in_thread_chunks(iter(range(12)), size=5)]
    assert chunks == [[0, 1, 2, 3, 4], [5, 6, 7, 8, 9], [10, 11]]
