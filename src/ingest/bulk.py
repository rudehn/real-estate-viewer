"""Bulk write helpers for snapshot tables.

Snapshot tables are replaced wholesale inside the caller's transaction, so a
failure anywhere (a parse error, a bad-row rejection, a lost connection)
rolls back to the previous snapshot.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable, Iterator
from itertools import islice

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncConnection

# Both SQLite (>= 3.32) and asyncpg allow 32,766 bind parameters per statement.
_PARAM_BUDGET = 30_000


def upsert(conn: AsyncConnection):
    """The dialect's INSERT construct that supports ON CONFLICT."""
    return pg_insert if conn.dialect.name == "postgresql" else sqlite_insert


def _chunk_size(table: sa.Table) -> int:
    return max(1, _PARAM_BUDGET // len(table.columns))


async def insert_rows(conn: AsyncConnection, table: sa.Table, rows: Iterable[dict]) -> int:
    """Insert rows in parameter-budget chunks.

    Rows are pulled in a worker thread (in_thread_chunks), so a generator that
    does CPU work per row keeps it off the event loop; the inserts themselves
    stay on the async connection.
    """
    written = 0
    async for chunk in in_thread_chunks(iter(rows), size=_chunk_size(table)):
        await conn.execute(sa.insert(table), chunk)
        written += len(chunk)
    return written


async def replace_rows(conn: AsyncConnection, table: sa.Table, rows: Iterable[dict]) -> int:
    await conn.execute(sa.delete(table))
    return await insert_rows(conn, table, rows)


async def in_thread_chunks(rows: Iterator, size: int = 5000) -> AsyncIterator[list]:
    """Pull rows from a CPU-bound generator in a worker thread, a chunk at a time.

    The generator is only ever advanced by one thread at a time, so ordinary
    (non-thread-safe) generators are fine.
    """
    while True:
        chunk = await asyncio.to_thread(lambda: list(islice(rows, size)))
        if not chunk:
            return
        yield chunk
