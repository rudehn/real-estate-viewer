import datetime as dt

from sqlmodel.ext.asyncio.session import AsyncSession

from db.models import Parcel, ParcelClass
from tests.api.conftest import sale


async def seed_distress(engine):
    async with AsyncSession(engine) as s:
        for pid in ("D1", "D2"):
            s.add(Parcel(parcel_id=pid, parcel_location=f"{pid} ST", parcel_class=ParcelClass.R,
                         acres=0.1))
        cheap = sale("D1", dt.date(2025, 5, 1), 50_000, buyer="BARGAIN LLC")
        cheap.assessed_total = 200_000
        nominal = sale("D2", dt.date(2025, 5, 2), 1_000, buyer="HEIR")
        nominal.assessed_total = 4_125_980
        s.add_all([cheap, nominal])
        await s.commit()


async def test_distressed_sales_skip_nominal_transfers(api, county_db):
    await seed_distress(county_db)
    body = (await api.get("/v2/distress/distressed-sales")).json()
    assert [r["parcel_id"] for r in body["rows"]] == ["D1"]
    assert body["rows"][0]["assessed_ratio"] == 0.25


async def test_distressed_sales_honor_dates(api, county_db):
    await seed_distress(county_db)
    body = (await api.get("/v2/distress/distressed-sales",
                          params={"date_from": "2025-06-01"})).json()
    assert body == {"applied_filters": ["date_from"], "rows": []}


async def test_stale_parcels(api):
    body = (await api.get("/v2/distress/stale-parcels")).json()
    assert "Z99 99999 9999" in [r["parcel_id"] for r in body["rows"]]
