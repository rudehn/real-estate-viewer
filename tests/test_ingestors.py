"""
Unit tests for CSV row parsing logic in db/ingestors.py.
These tests exercise the parsing edge cases without requiring a real database.
"""
import csv
import io
import datetime
import tempfile
import os

import pytest

from db.models import ParcelClass, SaleType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_csv(rows: list[dict]) -> str:
    """Build a CSV string from a list of dicts using the expected field names."""
    if not rows:
        return ""
    fieldnames = list(rows[0].keys())
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


BASE_ROW = {
    "PARID": "A01-001",
    "CONVNUM": "12345",
    "SALEDTE": "15-Jan-23",
    "PRICE": "150000",
    "OLDOWN": "SMITH JOHN",
    "OWNERNAME1": "DOE JANE",
    "PARCELLOCATION": "123 MAIN ST",
    "MAILINGNAME1": "DOE JANE",
    "PADDR1": "123 MAIN ST DAYTON OH",
    "CLS": "R",
    "ACRES": "0.25",
    "TAXLAND": "10000",
    "TAXBLDG": "40000",
    "TAXTOTAL": "50000",
    "ASMTLAND": "28571",
    "ASMTBLDG": "114286",
    "ASMTTOTL": "142857",
    "SALETYPE": "Land and Building",
    "SALEVALIDITY": "V",
    "DEEDREFERENCE": "OR123456",
    "NBHD": "1010",
}


async def ingest_csv_string(csv_str: str) -> tuple[list, list]:
    """Write csv_str to a temp file, run ingest_yearly_file, return (transactions, parcels)."""
    from db.ingestors import ingest_yearly_file
    from db.engine import engine
    from sqlmodel import SQLModel, select
    from sqlmodel.ext.asyncio.session import AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.ext.asyncio import create_async_engine
    from db.models import Transaction, Parcel

    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write(csv_str)
        tmp_path = f.name

    try:
        # Temporarily patch the engine used by ingestors
        import db.ingestors as ingestors_module
        original_engine = ingestors_module.engine
        ingestors_module.engine = test_engine

        await ingest_yearly_file(tmp_path)

        async_session = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as s:
            txns = (await s.exec(select(Transaction))).all()
            parcels = (await s.exec(select(Parcel))).all()

        ingestors_module.engine = original_engine
    finally:
        os.unlink(tmp_path)

    await test_engine.dispose()
    return txns, parcels


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_normal_row_is_parsed():
    """A well-formed residential row produces one transaction and one parcel."""
    csv_str = make_csv([BASE_ROW])
    txns, parcels = await ingest_csv_string(csv_str)

    assert len(txns) == 1
    assert len(parcels) == 1

    t = txns[0]
    assert t.parcel_id == "A01-001"
    assert t.sale_price == 150000.0
    assert t.sale_date == datetime.date(2023, 1, 15)
    assert t.parcel_class == ParcelClass.R
    assert t.acres == 0.25
    assert t.neighborhood == "1010"


async def test_missing_acres_defaults_to_zero():
    """When ACRES is blank, acres should default to 0.0 instead of raising."""
    row = {**BASE_ROW, "ACRES": ""}
    csv_str = make_csv([row])
    txns, _ = await ingest_csv_string(csv_str)

    assert len(txns) == 1
    assert txns[0].acres == 0.0


async def test_unknown_parcel_class_defaults_to_residential():
    """An unrecognised CLS code should fall back to ParcelClass.R."""
    row = {**BASE_ROW, "CLS": "X"}
    csv_str = make_csv([row])
    txns, _ = await ingest_csv_string(csv_str)

    assert len(txns) == 1
    assert txns[0].parcel_class == ParcelClass.R


async def test_bad_date_row_is_skipped():
    """A row with an unparseable date should be silently skipped."""
    bad_row = {**BASE_ROW, "SALEDTE": "not-a-date"}
    good_row = {**BASE_ROW, "PARID": "A01-002"}
    csv_str = make_csv([bad_row, good_row])
    txns, _ = await ingest_csv_string(csv_str)

    # Only the good row should be committed
    assert len(txns) == 1
    assert txns[0].parcel_id == "A01-002"


async def test_empty_row_is_skipped():
    """A row where all values are blank should be silently skipped."""
    empty_row = {k: "" for k in BASE_ROW}
    csv_str = make_csv([empty_row, BASE_ROW])
    txns, _ = await ingest_csv_string(csv_str)

    assert len(txns) == 1


async def test_duplicate_file_is_not_reingested():
    """Running ingest_yearly_file twice on the same file should not double-insert."""
    from db.ingestors import ingest_yearly_file
    from sqlmodel import select
    from sqlmodel.ext.asyncio.session import AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlmodel import SQLModel
    from db.models import Transaction
    import db.ingestors as ingestors_module

    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    csv_str = make_csv([BASE_ROW])
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write(csv_str)
        tmp_path = f.name

    try:
        original_engine = ingestors_module.engine
        ingestors_module.engine = test_engine

        await ingest_yearly_file(tmp_path)
        await ingest_yearly_file(tmp_path)  # second call should be a no-op

        async_session = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as s:
            txns = (await s.exec(select(Transaction))).all()

        ingestors_module.engine = original_engine
    finally:
        os.unlink(tmp_path)

    await test_engine.dispose()
    assert len(txns) == 1


async def test_same_row_in_two_files_is_inserted_once():
    """Weekly ZIPs overlap the yearly files; identical rows must dedup."""
    from db.ingestors import ingest_yearly_file
    from sqlmodel import SQLModel, select
    from sqlmodel.ext.asyncio.session import AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.ext.asyncio import create_async_engine
    from db.models import Transaction
    import db.ingestors as ingestors_module

    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    # The same sale plus one new sale, arriving via a second file
    other_row = {**BASE_ROW, "CONVNUM": "99999", "PRICE": "225000"}
    paths = []
    for rows in ([BASE_ROW], [BASE_ROW, other_row]):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write(make_csv(rows))
            paths.append(f.name)

    try:
        original_engine = ingestors_module.engine
        ingestors_module.engine = test_engine

        for p in paths:
            await ingest_yearly_file(p)

        async_session = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as s:
            txns = (await s.exec(select(Transaction))).all()

        ingestors_module.engine = original_engine
    finally:
        for p in paths:
            os.unlink(p)

    await test_engine.dispose()
    assert len(txns) == 2
    assert sorted(t.sale_price for t in txns) == [150000.0, 225000.0]


async def test_maintenance_dedupes_existing_rows():
    """ensure_transaction_dedup removes pre-index duplicates and is idempotent."""
    from sqlalchemy import text as sa_text
    from sqlmodel import SQLModel, select
    from sqlmodel.ext.asyncio.session import AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.ext.asyncio import create_async_engine
    from db.models import Parcel, Transaction
    import db.maintenance as maintenance_module

    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
        # Simulate a database from before the unique index existed
        await conn.execute(sa_text("DROP INDEX uq_transaction_natural"))

    async_session = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as s:
        s.add(Parcel(parcel_id="P1", parcel_location="1 ELM ST",
                     parcel_class=ParcelClass.R, acres=0.2))
        for _ in range(3):
            s.add(Transaction(
                parcel_id="P1", conv_num=42, sale_date=datetime.date(2023, 1, 1),
                sale_price=100000.0, old_owner="A", new_owner="B",
                parcel_location="1 ELM ST", mailing_name="B", mailing_address="X",
                parcel_class=ParcelClass.R, acres=0.2,
                taxable_land=1, taxable_building=1, taxable_total=2,
                assessed_land=None, assessed_building=None, assessed_total=None,
                sale_type=None, sale_validity=None, deed_reference=None,
                neighborhood=None,
            ))
        await s.commit()

    original_engine = maintenance_module.engine
    maintenance_module.engine = test_engine
    try:
        await maintenance_module.ensure_transaction_dedup()
        await maintenance_module.ensure_transaction_dedup()  # idempotent
    finally:
        maintenance_module.engine = original_engine

    async with async_session() as s:
        txns = (await s.exec(select(Transaction))).all()
    await test_engine.dispose()
    assert len(txns) == 1
