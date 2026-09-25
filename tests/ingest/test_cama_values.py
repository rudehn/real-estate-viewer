from pathlib import Path

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from db.county_models import Neighborhood, ParcelValue, TaxDistrict
from ingest.cama_ingest import appeal_year, ingest_cama, value_method

FIXTURE = Path(__file__).parent.parent / "fixtures" / "county" / "cama_fixture.zip"


def test_value_method_and_appeal_year():
    assert value_method("1") == "cost"
    assert value_method("3") == "override"
    assert value_method("4") == "income"
    assert value_method(None) is None
    assert appeal_year("B20") == 2020
    assert appeal_year("B96") == 1996
    assert appeal_year("TIF") is None
    assert appeal_year(None) is None


async def test_values(db_engine):
    counts = await ingest_cama(FIXTURE, engine=db_engine)
    assert counts["parcel_value"] == 4
    async with AsyncSession(db_engine) as s:
        rural = await s.get(ParcelValue, "A01 00101 0001")
        dayton = await s.get(ParcelValue, "R72 00304 0025")
        ranch = await s.get(ParcelValue, "N64 00101 0003")
    assert (rural.land_2025, rural.building_2025, rural.total_2025) == (73980, 200340, 274320)
    assert (rural.land_2026, rural.building_2026, rural.total_2026) == (85370, 182190, 267560)
    assert rural.change_pct == pytest.approx(-2.464, abs=1e-3)
    assert rural.reappraisal_reason == "REAPPRAISAL"
    assert (rural.value_method, rural.tif) == ("cost", False)
    assert (dayton.tif, dayton.value_method) == (True, "override")
    assert ranch.change_pct == pytest.approx(18.699, abs=1e-3)


async def test_neighborhoods_and_districts(db_engine):
    await ingest_cama(FIXTURE, engine=db_engine)
    async with AsyncSession(db_engine) as s:
        butler = await s.get(Neighborhood, "48150000")
        districts = {d.code: d for d in (await s.exec(select(TaxDistrict))).all()}
    assert (butler.name, butler.display_name, butler.tax_district) == (
        "N BUTLER TWP", "N BUTLER TWP", "A01"
    )
    assert set(districts) == {"A01", "N64", "R72"}
    assert districts["R72"].jurisdiction == "DAYTON"
