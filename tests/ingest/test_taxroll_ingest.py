from pathlib import Path

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from db.county_models import ParcelTax
from db.models import Parcel, ParcelClass
from ingest.taxroll_ingest import classify_occupancy, ingest_taxroll

FIXTURE = Path(__file__).parent.parent / "fixtures" / "county" / "TAXROLL_20260923.zip"


@pytest.mark.parametrize(
    ("kwargs", "category"),
    [
        (dict(owner_occupied=True, homestead=False, owner_name="VB ELEVEN LLC"), "owner_occupied"),
        (dict(owner_occupied=False, homestead=True, owner_name="SMITH JOHN"), "owner_occupied"),
        (dict(owner_occupied=False, homestead=False, owner_name="CITY OF DAYTON"), "government"),
        (dict(owner_occupied=False, homestead=False, owner_name="VB ELEVEN LLC"), "company"),
        (dict(owner_occupied=False, homestead=False, owner_name="SMITH FAMILY TRUST"), "trust"),
        (dict(owner_occupied=False, homestead=False, owner_name="SMITH JOHN",
              mailing_address1="PO BOX 12", situs="10 ELM ST"), "absentee_individual"),
        (dict(owner_occupied=False, homestead=False, owner_name="SMITH JOHN",
              mailing_address1="10 elm st.", situs="10 ELM ST"), "unknown"),
    ],
)
def test_classify_occupancy(kwargs, category):
    kwargs = {"mailing_address1": None, "situs": None, **kwargs}
    got, reason = classify_occupancy(**kwargs)
    assert got == category
    assert reason


async def test_ingest_taxroll(db_engine):
    async with AsyncSession(db_engine) as s:
        s.add(Parcel(parcel_id="A01 00101 0001", parcel_location="11974 FREDERICK PIKE",
                     parcel_class=ParcelClass.R, acres=2.0))
        await s.commit()
    assert await ingest_taxroll(FIXTURE, engine=db_engine) == 4
    async with AsyncSession(db_engine) as s:
        row = await s.get(ParcelTax, "A01 00101 0001")
        parcel = await s.get(Parcel, "A01 00101 0001")
        count = len((await s.exec(select(ParcelTax))).all())
    assert count == 4
    assert row.annual_bill == pytest.approx(6066.22)
    assert (row.tax_year, row.owner_occupied, row.occupancy) == (2025, True, "owner_occupied")
    assert row.owner_name == "MULLENAX SAMANTHA MARIE"
    assert row.mailing_state == "OH"
    assert row.out_of_state is False
    assert row.mailing_address == "11974 FREDERICK PIKE, VANDALIA OH 45377"
    assert parcel.census_tract == "39113-110100-1"


async def test_reingest_replaces_rows(db_engine):
    await ingest_taxroll(FIXTURE, engine=db_engine)
    await ingest_taxroll(FIXTURE, engine=db_engine)
    async with AsyncSession(db_engine) as s:
        assert len((await s.exec(select(ParcelTax))).all()) == 4
