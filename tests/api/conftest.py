import datetime as dt
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from api.cache import cache
from db.engine import get_session
from db.models import Parcel, ParcelClass, Transaction
from derived.summary import rebuild_derived
from ingest.cama_ingest import ingest_cama
from ingest.taxroll_ingest import ingest_taxroll
from main import app

FIXTURES = Path(__file__).parent.parent / "fixtures" / "county"


def sale(parcel_id, day, price, buyer="BUYER A", seller="SELLER B", validity="VALID SALE",
         cls=ParcelClass.R):
    return Transaction(
        parcel_id=parcel_id, sale_date=day, sale_price=price, old_owner=seller, new_owner=buyer,
        parcel_location="X", mailing_name=buyer, mailing_address="X", parcel_class=cls,
        acres=0.1, taxable_land=0, taxable_building=0, taxable_total=0, sale_validity=validity,
    )


SALES = [
    ("N64 00101 0003", dt.date(2019, 5, 1), 90_000, "SMITH JOHN", "OLD OWNER"),
    ("N64 00101 0003", dt.date(2025, 6, 1), 150_000, "JONES MARY", "SMITH JOHN"),
    ("N64 00101 0003", dt.date(2025, 9, 1), 1, "JONES HEIR", "JONES MARY"),
    ("R72 00304 0025", dt.date(2024, 3, 15), 300_000, "BUYER R", "SELLER R"),
    ("R72 00304 0025", dt.date(2025, 8, 20), 330_000, "BUYER S", "BUYER R"),
    ("A01 00101 0001", dt.date(2023, 3, 20), 320_000, "MULLENAX SAMANTHA MARIE", "PRIOR OWNER"),
    ("A01 00101 0001", dt.date(2025, 7, 1), 900_000, "FUND LLC", "MULLENAX SAMANTHA MARIE"),
    ("A01 00102 0069", dt.date(2025, 7, 1), 900_000, "FUND LLC", "SELLER C"),
    ("Z99 99999 9999", dt.date(2010, 1, 1), 50_000, "GONE OWNER", "OLDER OWNER"),
]


@pytest.fixture
async def county_db(db_engine, tmp_path, monkeypatch):
    import derived.mapbinary as mb

    monkeypatch.setattr(mb, "DERIVED_DIR", tmp_path / "derived")
    cache.clear()
    async with AsyncSession(db_engine) as s:
        s.add(Parcel(parcel_id="Z99 99999 9999", parcel_location="1 GONE ST",
                     parcel_class=ParcelClass.R, acres=0.1))
        await s.commit()
    await ingest_cama(FIXTURES / "cama_fixture.zip", engine=db_engine)
    await ingest_taxroll(FIXTURES / "TAXROLL_20260923.zip", engine=db_engine)
    async with AsyncSession(db_engine) as s:
        s.add_all([sale(*row) for row in SALES])
        await s.commit()
    await rebuild_derived(engine=db_engine)
    return db_engine


@pytest.fixture
async def api(county_db):
    async def override():
        async with AsyncSession(county_db, expire_on_commit=False) as s:
            yield s

    app.dependency_overrides[get_session] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
    cache.clear()
