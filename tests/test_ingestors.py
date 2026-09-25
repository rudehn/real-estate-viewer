"""
Unit tests for CSV row parsing logic in db/ingestors.py.
These tests exercise the parsing edge cases without requiring a real database.
"""
import csv
import datetime
import io
import os
import tempfile

from db.models import ParcelClass

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
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.orm import sessionmaker
    from sqlmodel import SQLModel, select
    from sqlmodel.ext.asyncio.session import AsyncSession

    from db.ingestors import ingest_yearly_file
    from db.models import Parcel, Transaction

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
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.orm import sessionmaker
    from sqlmodel import SQLModel, select
    from sqlmodel.ext.asyncio.session import AsyncSession

    import db.ingestors as ingestors_module
    from db.ingestors import ingest_yearly_file
    from db.models import Transaction

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
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.orm import sessionmaker
    from sqlmodel import SQLModel, select
    from sqlmodel.ext.asyncio.session import AsyncSession

    import db.ingestors as ingestors_module
    from db.ingestors import ingest_yearly_file
    from db.models import Transaction

    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    # The same sale plus one new sale, arriving via a second file
    other_row = {**BASE_ROW, "CONVNUM": "99999", "PRICE": "225000"}
    paths = []
    for rows in ([BASE_ROW], [BASE_ROW, other_row]):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
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


# ---------------------------------------------------------------------------
# Encoding: the county exports are not always UTF-8
# ---------------------------------------------------------------------------

# SALES_20260913_TO_20260919.zip carried a cp1252 non-breaking space (0xA0)
# inside a mailing name, which is invalid UTF-8.
NBSP_ROW = {**BASE_ROW, "MAILINGNAME1": "JUSTIN\xa0GOTTUSO", "OWNERNAME1": "JUST\xa0IN LLC"}


def make_cp1252_csv(rows: list[dict]) -> bytes:
    return make_csv(rows).encode("cp1252")


async def _ingest_into_memory(ingest):
    """Run ``ingest()`` against a fresh in-memory DB; return its transactions."""
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.orm import sessionmaker
    from sqlmodel import SQLModel, select
    from sqlmodel.ext.asyncio.session import AsyncSession

    import db.ingestors as ingestors_module
    from db.models import Transaction

    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    original_engine = ingestors_module.engine
    ingestors_module.engine = test_engine
    try:
        await ingest()
        async_session = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as s:
            return (await s.exec(select(Transaction))).all()
    finally:
        ingestors_module.engine = original_engine
        await test_engine.dispose()


async def test_weekly_zip_with_cp1252_bytes_is_ingested():
    """A weekly ZIP whose CSV is not valid UTF-8 must still be ingested."""
    import zipfile

    from db.ingestors import _ingest_weekly_zip

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("SALES_20260913_TO_20260919.csv", make_cp1252_csv([NBSP_ROW]))

    txns = await _ingest_into_memory(
        lambda: _ingest_weekly_zip("SALES_20260913_TO_20260919.zip", buf.getvalue())
    )

    assert len(txns) == 1
    # NBSP is normalised to a plain space so owner-name matching still works
    assert txns[0].mailing_name == "JUSTIN GOTTUSO"
    assert txns[0].new_owner == "JUST IN LLC"


async def test_yearly_file_with_cp1252_bytes_is_ingested():
    """A yearly CSV that is not valid UTF-8 must be ingested, not crash the run."""
    from db.ingestors import ingest_yearly_file

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(make_cp1252_csv([NBSP_ROW]))
        tmp_path = f.name
    try:
        txns = await _ingest_into_memory(lambda: ingest_yearly_file(tmp_path))
    finally:
        os.unlink(tmp_path)

    assert len(txns) == 1
    assert txns[0].mailing_name == "JUSTIN GOTTUSO"


def test_decode_csv_prefers_utf8():
    """Genuine UTF-8 (with or without BOM) must not be mis-decoded as cp1252."""
    from db.ingestors import _decode_csv

    assert _decode_csv("\ufeffPARID,NAME\nA1,JOSÉ\n".encode()) == "PARID,NAME\nA1,JOSÉ\n"
    assert _decode_csv("PARID,NAME\nA1,JOSÉ\n".encode("cp1252")) == "PARID,NAME\nA1,JOSÉ\n"
