"""How repeated county snapshots of the same sale are reconciled.

The county publishes each sale several times: in one or more weekly ZIPs
shortly after recording, then in every monthly re-export of the yearly file.
Snapshots drift - the weekly OWNERNAME1 is often whoever owns the parcel at
export time rather than the buyer, and weekly files carry no NBHD or
DEEDREFERENCE at all - so the yearly export is authoritative.
"""
import datetime
import io
import zipfile

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

import db.ingestors as ingestors_module
from db.models import DataFile, Transaction

from .test_ingestors import BASE_ROW, make_csv

WEEKLY_ROW = {k: v for k, v in BASE_ROW.items() if k not in ("NBHD", "DEEDREFERENCE")}


@pytest.fixture
async def engine(monkeypatch):
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    monkeypatch.setattr(ingestors_module, "engine", test_engine)
    yield test_engine
    await test_engine.dispose()


async def rows(engine, model=Transaction):
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as s:
        return (await s.exec(select(model).order_by(model.id))).all()


async def ingest_yearly(tmp_path, rows_, name="SALES_2023_RES.csv", subdir="yearly"):
    path = tmp_path / subdir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(make_csv(rows_))
    await ingestors_module.ingest_yearly_file(str(path))
    return path


async def ingest_weekly(rows_, name="SALES_20230115_TO_20230121.zip"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(name.replace(".zip", ".csv"), make_csv(rows_))
    await ingestors_module._ingest_weekly_zip(name, buf.getvalue())


# ---------------------------------------------------------------------------
# Yearly re-exports
# ---------------------------------------------------------------------------

async def test_changed_yearly_export_is_reingested_in_place(engine, tmp_path):
    """The current-year file is re-exported monthly under the same name; a new
    export must be ingested, updating existing sales rather than duplicating."""
    await ingest_yearly(tmp_path, [BASE_ROW])
    original_id = (await rows(engine))[0].id

    corrected = {**BASE_ROW, "OWNERNAME1": "DOE JANE AND JOHN", "SALEVALIDITY": "VALID SALE"}
    later_sale = {**BASE_ROW, "CONVNUM": "12400", "SALEDTE": "20-Feb-23", "PRICE": "90000"}
    await ingest_yearly(tmp_path, [corrected, later_sale])

    txns = await rows(engine)
    assert len(txns) == 2
    assert txns[0].id == original_id
    assert txns[0].new_owner == "DOE JANE AND JOHN"
    assert txns[0].sale_validity == "VALID SALE"


async def test_unchanged_yearly_export_is_skipped(engine, tmp_path):
    await ingest_yearly(tmp_path, [BASE_ROW])
    first = (await rows(engine, DataFile))[0].ingested_at
    await ingest_yearly(tmp_path, [BASE_ROW])

    files = await rows(engine, DataFile)
    assert len(files) == 1
    assert files[0].ingested_at == first


async def test_yearly_file_identity_ignores_data_dir(engine, tmp_path):
    """Moving DATA_DIR must not make every yearly file look new."""
    await ingest_yearly(tmp_path, [BASE_ROW], subdir="old-dir/yearly")
    await ingest_yearly(tmp_path, [BASE_ROW], subdir="new-dir/yearly/SALES_2023")

    files = await rows(engine, DataFile)
    assert [f.filename for f in files] == ["SALES_2023_RES.csv"]


def test_file_key_handles_backslash_zip_paths():
    """The county's yearly ZIPs use backslash separators, which POSIX extracts
    as a literal backslash inside one file name."""
    assert ingestors_module._file_key("/ingest/yearly/SALES_2026\\SALES_2026_RES.csv") == (
        "SALES_2026_RES.csv"
    )


# ---------------------------------------------------------------------------
# Weekly vs yearly precedence
# ---------------------------------------------------------------------------

async def test_yearly_overwrites_earlier_weekly_snapshot(engine, tmp_path):
    weekly = {**WEEKLY_ROW, "OWNERNAME1": "CURRENT OWNER LLC", "MAILINGNAME1": "SMITH JOHN"}
    await ingest_weekly([weekly])
    await ingest_yearly(tmp_path, [BASE_ROW])

    txns = await rows(engine)
    assert len(txns) == 1
    t = txns[0]
    assert (t.new_owner, t.mailing_name, t.neighborhood, t.deed_reference) == (
        "DOE JANE", "DOE JANE", "1010", "OR123456",
    )
    assert t.source == "yearly"


async def test_weekly_does_not_overwrite_yearly(engine, tmp_path):
    await ingest_yearly(tmp_path, [BASE_ROW])
    await ingest_weekly([{**WEEKLY_ROW, "OWNERNAME1": "CURRENT OWNER LLC"}])

    txns = await rows(engine)
    assert len(txns) == 1
    assert txns[0].new_owner == "DOE JANE"
    assert txns[0].source == "yearly"


async def test_weekly_row_superseded_by_yearly_is_pruned(engine, tmp_path):
    """If the seller name drifted between snapshots the rows don't share a key;
    the yearly row for the same conveyance still supersedes the weekly one."""
    await ingest_weekly([{**WEEKLY_ROW, "OLDOWN": "SMITH JOHN A"}])
    await ingest_yearly(tmp_path, [BASE_ROW])

    txns = await rows(engine)
    assert [(t.old_owner, t.source) for t in txns] == [("SMITH JOHN", "yearly")]


async def test_weekly_only_sales_are_kept(engine, tmp_path):
    """Sales newer than the last yearly export exist only in weekly files."""
    await ingest_yearly(tmp_path, [BASE_ROW])
    await ingest_weekly([{**WEEKLY_ROW, "CONVNUM": "13000", "SALEDTE": "25-Mar-23"}])

    assert len(await rows(engine)) == 2


async def test_weekly_row_inherits_parcel_neighborhood(engine, tmp_path):
    """Weekly files have no NBHD column; a parcel's neighborhood doesn't change
    between sales, so take it from the parcel's history."""
    await ingest_yearly(tmp_path, [BASE_ROW])
    await ingest_weekly([{**WEEKLY_ROW, "CONVNUM": "13000", "SALEDTE": "25-Mar-23"}])

    txns = await rows(engine)
    assert [t.neighborhood for t in txns] == ["1010", "1010"]



async def test_weekly_row_gets_neighborhood_from_later_history(engine, tmp_path):
    """The parcel's history may only arrive after the weekly row (e.g. a later
    yearly file for an earlier year); the weekly row must still be filled."""
    await ingest_weekly([{**WEEKLY_ROW, "CONVNUM": "13000", "SALEDTE": "25-Mar-23"}])
    earlier_sale = {**BASE_ROW, "SALEDTE": "15-Jan-22"}
    await ingest_yearly(tmp_path, [earlier_sale], name="SALES_2022_RES.csv")

    assert [t.neighborhood for t in await rows(engine)] == ["1010", "1010"]

# ---------------------------------------------------------------------------
# Distinct sales that must never be merged
# ---------------------------------------------------------------------------

async def test_same_day_chained_conveyances_are_kept(engine, tmp_path):
    """The county occasionally records two same-day conveyances of one parcel
    under one conv_num (e.g. owner -> HUD -> HUD); they differ by seller."""
    hud = {**BASE_ROW, "OLDOWN": "DOE JANE", "OWNERNAME1": "SECRETARY OF H U D", "PRICE": "0"}
    await ingest_yearly(tmp_path, [BASE_ROW, hud])
    await ingest_yearly(tmp_path, [BASE_ROW, hud], name="SALES_2023_COM.csv")

    assert len(await rows(engine)) == 2


async def test_legacy_rows_without_conv_num_are_kept(engine, tmp_path):
    """2001-2002 files have no CONVNUM; same-day resales on one parcel are
    distinct sales."""
    first = {**BASE_ROW, "CONVNUM": "", "SALEDTE": "09-Sep-02"}
    resale = {**first, "OLDOWN": "DOE JANE", "OWNERNAME1": "ROE RICHARD", "PRICE": "180000"}
    await ingest_yearly(tmp_path, [first, resale], name="SALES_2002_RES.csv")
    await ingest_yearly(tmp_path, [first, resale, {**first, "PARID": "B02"}],
                        name="SALES_2002_RES.csv")

    txns = await rows(engine)
    assert len(txns) == 3
    assert all(t.conv_num is None for t in txns)
    assert {t.sale_date for t in txns} == {datetime.date(2002, 9, 9)}


async def test_duplicate_rows_within_one_yearly_file(engine, tmp_path):
    """A repeated row inside one file must not trip Postgres's "ON CONFLICT DO
    UPDATE command cannot affect row a second time"."""
    await ingest_yearly(tmp_path, [BASE_ROW, BASE_ROW])
    assert len(await rows(engine)) == 1

