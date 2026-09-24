"""Startup schema repair (db/maintenance.py) for databases created by older code.

Production never runs alembic, so ensure_schema() must bring any earlier
database up to date in place, and be a cheap no-op once it has.
"""
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel

import db.maintenance as maintenance_module

LEGACY_INDEX = """
    CREATE UNIQUE INDEX uq_transaction_natural ON "transaction"
    (parcel_id, sale_date, sale_price, old_owner, new_owner, coalesce(conv_num, -1))
"""


def _txn(conv_num, old_owner, new_owner, price=100000):
    conv = "NULL" if conv_num is None else conv_num
    return f"""
        INSERT INTO "transaction" (parcel_id, conv_num, sale_date, sale_price, old_owner,
            new_owner, parcel_location, mailing_name, mailing_address, parcel_class, acres,
            taxable_land, taxable_building, taxable_total)
        VALUES ('P1', {conv}, '2023-01-15', {price}, '{old_owner}', '{new_owner}',
            '1 ELM ST', 'X', 'X', 'R', 0.2, 1, 1, 2)
    """


@pytest.fixture
async def engine(monkeypatch):
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    monkeypatch.setattr(maintenance_module, "engine", test_engine)
    yield test_engine
    await test_engine.dispose()


@pytest.fixture
async def legacy_engine(engine):
    """A database as the pre-snapshot-reconciliation code left it."""
    async with engine.begin() as conn:
        for stmt in (
            "DROP INDEX uq_transaction_conveyance",
            "DROP INDEX uq_transaction_legacy",
            'ALTER TABLE "transaction" DROP COLUMN source',
            "ALTER TABLE datafile DROP COLUMN content_hash",
            LEGACY_INDEX,
            "INSERT INTO parcel (parcel_id, parcel_location, parcel_class, acres)"
            " VALUES ('P1', '1 ELM ST', 'R', 0.2)",
            # Two snapshots of one conveyance whose buyer name drifted
            _txn(42, "SMITH JOHN", "DOE JANE"),
            _txn(42, "SMITH JOHN", "CURRENT OWNER LLC"),
            # A same-day chained conveyance under the same conv_num
            _txn(42, "DOE JANE", "SECRETARY OF H U D", price=0),
            # 2001-2002 style rows: no conv_num, genuinely distinct sales
            _txn(None, "A", "B"),
            _txn(None, "B", "C", price=150000),
            "INSERT INTO datafile (filename, ingested_at) VALUES"
            " ('/ingest/yearly/SALES_2023_RES.csv', '2026-01-01'),"
            " ('SALES_20230115_TO_20230121.zip', '2026-01-02')",
        ):
            await conn.execute(text(stmt))
    return engine


async def _query(engine, sql):
    async with engine.connect() as conn:
        return (await conn.execute(text(sql))).all()


async def _index_names(engine):
    rows = await _query(engine, "SELECT name FROM sqlite_master WHERE type = 'index'")
    return {r[0] for r in rows}


async def test_legacy_database_is_repaired(legacy_engine):
    await maintenance_module.ensure_schema()
    await maintenance_module.ensure_schema()  # idempotent

    txns = await _query(
        legacy_engine,
        'SELECT conv_num, old_owner, new_owner, source FROM "transaction" ORDER BY id',
    )
    assert txns == [
        (42, "SMITH JOHN", "DOE JANE", "weekly"),
        (42, "DOE JANE", "SECRETARY OF H U D", "weekly"),
        (None, "A", "B", "weekly"),
        (None, "B", "C", "weekly"),
    ]

    indexes = await _index_names(legacy_engine)
    assert {"uq_transaction_conveyance", "uq_transaction_legacy"} <= indexes
    assert "uq_transaction_natural" not in indexes

    # Yearly files are forgotten so the next run re-ingests them from disk,
    # which relabels their rows authoritative; weekly ZIPs are never re-fetched.
    files = await _query(legacy_engine, "SELECT filename, content_hash FROM datafile")
    assert files == [("SALES_20230115_TO_20230121.zip", None)]


async def test_fresh_database_is_left_alone(engine):
    async with engine.begin() as conn:
        await conn.execute(text(
            "INSERT INTO datafile (filename, ingested_at, content_hash)"
            " VALUES ('SALES_2023_RES.csv', '2026-01-01', 'abc')"
        ))
    before = await _index_names(engine)

    await maintenance_module.ensure_schema()

    assert await _index_names(engine) == before
    assert len(await _query(engine, "SELECT * FROM datafile")) == 1
