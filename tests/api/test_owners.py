import datetime as dt

import sqlalchemy as sa
from sqlmodel.ext.asyncio.session import AsyncSession

from db.county_models import ParcelSummary
from db.models import Parcel, ParcelClass
from derived.summary import bump_data_version
from tests.api.conftest import sale


async def get(api, path, **params):
    r = await api.get(path, params=params)
    assert r.status_code == 200, r.text
    return r.json()


async def test_top_owners_are_current_owners(api):
    body = await get(api, "/v2/owners/top", order_by="value")
    mullenax = next(r for r in body["rows"] if r["owner_name"] == "MULLENAX SAMANTHA MARIE")
    assert (mullenax["parcel_count"], mullenax["total_market_value"]) == (1, 267_560)


async def test_top_owners_honor_parcel_filters(api):
    body = await get(api, "/v2/owners/top", neighborhood="48150000", price_min=1)
    assert body["applied_filters"] == ["price_min", "neighborhood"]


async def test_owner_detail(api):
    body = await get(api, "/v2/owners/MULLENAX SAMANTHA MARIE")
    assert [h["parcel_id"] for h in body["holdings"]] == ["A01 00101 0001"]
    assert body["totals"]["parcel_count"] == 1
    assert body["profile"]["total_buys"] == 1
    assert body["profile"]["total_sells"] == 1


async def test_past_owner_without_holdings_still_resolves(api):
    body = await get(api, "/v2/owners/FUND LLC")
    assert body["holdings"] == []
    assert body["profile"]["total_buys"] == 2


async def test_unknown_owner_is_404(api):
    r = await api.get("/v2/owners/NOBODY AT ALL")
    assert r.status_code == 404


async def test_acquisition_wave(api, county_db):
    async with AsyncSession(county_db) as s:
        for i in range(5):
            s.add(Parcel(parcel_id=f"W{i}", parcel_location=f"W{i} ST",
                         parcel_class=ParcelClass.R, acres=0.1))
            s.add(sale(f"W{i}", dt.date(2025, 1, 1) + dt.timedelta(days=10 * i), 80_000 + i,
                       buyer="WAVE LLC", seller=f"S{i}"))
        await s.commit()
    body = await get(api, "/v2/investors/acquisition-waves", date_from="2024-01-01")
    assert body["applied_filters"] == ["date_from"]
    assert [r["owner_name"] for r in body["rows"]] == ["WAVE LLC"]
    assert body["rows"][0]["acquisition_count"] == 5


async def test_net_sellers_and_absentee_shapes(api):
    for path in ("/v2/investors/net-sellers", "/v2/investors/absentee-owners"):
        body = await get(api, path)
        assert set(body) == {"applied_filters", "rows"}


async def test_top_owners_are_cached_per_data_version(api, county_db):
    """The aggregate scans every parcel, so it is served from the versioned cache."""
    async def names():
        body = await get(api, "/v2/owners/top", limit=100)
        return {r["owner_name"] for r in body["rows"]}

    assert "MULLENAX SAMANTHA MARIE" in await names()
    async with county_db.begin() as conn:
        ps = ParcelSummary.__table__
        await conn.execute(sa.update(ps).where(ps.c.owner_name == "MULLENAX SAMANTHA MARIE")
                           .values(owner_name="NEW OWNER LLC"))
    assert "MULLENAX SAMANTHA MARIE" in await names()
    async with county_db.begin() as conn:
        await bump_data_version(conn)
    assert "NEW OWNER LLC" in await names()
