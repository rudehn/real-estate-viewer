import datetime as dt

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from api.cache import cache
from db.county_models import Dwelling, ParcelSummary
from db.engine import get_session
from db.models import Parcel, ParcelClass, Transaction
from main import app

SNAP = dt.date(2026, 8, 31)


def home(pid, nbhd, sqft, beds, baths, year, style, lat, lng, sale=None, buyer="B",
         assessed=None):
    rows = [
        Parcel(parcel_id=pid, parcel_location=f"{pid} ST", parcel_class=ParcelClass.R, acres=0.1,
               neighborhood=nbhd, latitude=lat, longitude=lng),
        ParcelSummary(parcel_id=pid, parcel_class="R", neighborhood=nbhd, latitude=lat,
                      longitude=lng, address=f"{pid} ST", living_sqft=sqft, beds=beds,
                      baths=float(baths), year_built=year, occupancy="unknown"),
        Dwelling(parcel_id=pid, card=1, living_sqft=sqft, beds=beds, full_baths=baths,
                 half_baths=0, year_built=year, style_code=style, snapshot_date=SNAP),
    ]
    if sale:
        rows.append(Transaction(
            parcel_id=pid, sale_date=sale[0], sale_price=sale[1], old_owner="S", new_owner=buyer,
            parcel_location="X", mailing_name=buyer, mailing_address="X",
            parcel_class=ParcelClass.R, acres=0.1, taxable_land=0, taxable_building=0,
            taxable_total=0, assessed_total=assessed, sale_validity="VALID SALE"))
    return rows


@pytest.fixture
async def comps_api(db_engine):
    cache.clear()

    async def override():
        async with AsyncSession(db_engine, expire_on_commit=False) as s:
            yield s

    app.dependency_overrides[get_session] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c, db_engine
    app.dependency_overrides.clear()
    cache.clear()


async def add(engine, *groups):
    async with AsyncSession(engine) as s:
        for group in groups:
            s.add_all(group)
        await s.commit()


async def test_neighborhood_comps_ranked_by_similarity(comps_api):
    api, engine = comps_api
    d = dt.date(2026, 6, 1)
    await add(
        engine,
        home("S", "NB1", 1500, 3, 2, 1960, "03", 39.70, -84.10),
        home("C1", "NB1", 1510, 3, 2, 1960, "03", 39.701, -84.10, (d, 200_000), "B1"),
        home("C2", "NB1", 1650, 3, 2, 1962, "03", 39.702, -84.10, (d, 210_000), "B2"),
        home("C3", "NB1", 1400, 3, 2, 1958, "03", 39.703, -84.10, (d, 190_000), "B3"),
        home("C4", "NB1", 1550, 4, 2, 1965, "03", 39.704, -84.10, (d, 205_000), "B4"),
        home("C5", "NB1", 1450, 3, 1, 1955, "03", 39.705, -84.10, (d, 185_000), "B5"),
        home("BIG", "NB1", 2400, 3, 2, 1960, "03", 39.706, -84.10, (d, 400_000), "B6"),
        home("COLONIAL", "NB1", 1500, 3, 2, 1960, "07", 39.707, -84.10, (d, 250_000), "B7"),
        home("OLD", "NB1", 1500, 3, 2, 1960, "03", 39.708, -84.10,
             (dt.date(2023, 1, 1), 150_000), "B8"),
    )
    body = (await api.get("/v2/parcels/S/comps")).json()
    assert body["basis"] == "neighborhood"
    ids = [c["parcel_id"] for c in body["comps"]]
    assert ids[0] == "C1"
    assert set(ids) == {"C1", "C2", "C3", "C4", "C5"}
    assert body["median_price"] == 200_000


async def test_widens_to_radius_when_neighborhood_is_thin(comps_api):
    api, engine = comps_api
    d = dt.date(2026, 6, 1)
    await add(
        engine,
        home("S", "NB1", 1500, 3, 2, 1960, "03", 39.70, -84.10),
        home("C1", "NB1", 1500, 3, 2, 1960, "03", 39.701, -84.10, (d, 200_000), "B1"),
        home("NEAR", "NB2", 1500, 3, 2, 1960, "03", 39.705, -84.10, (d, 210_000), "B2"),
        home("FAR", "NB3", 1500, 3, 2, 1960, "03", 39.80, -84.10, (d, 220_000), "B3"),
    )
    body = (await api.get("/v2/parcels/S/comps")).json()
    assert body["basis"] == "radius"
    ids = {c["parcel_id"] for c in body["comps"]}
    assert ids == {"C1", "NEAR"}
    near = next(c for c in body["comps"] if c["parcel_id"] == "NEAR")
    assert near["distance_miles"] == pytest.approx(0.345, abs=0.01)


async def test_no_dwelling_means_no_comps(comps_api):
    api, engine = comps_api
    async with AsyncSession(engine) as s:
        s.add(Parcel(parcel_id="LOT", parcel_location="LOT ST", parcel_class=ParcelClass.R,
                     acres=0.2))
        await s.commit()
    body = (await api.get("/v2/parcels/LOT/comps")).json()
    assert (body["basis"], body["comps"]) == ("none", [])
    assert body["message"] == "No dwelling on record to compare"


async def test_nominal_price_is_not_a_comp(comps_api):
    api, engine = comps_api
    d = dt.date(2026, 6, 1)
    await add(
        engine,
        home("S", "NB1", 1500, 3, 2, 1960, "03", 39.70, -84.10),
        home("C1", "NB1", 1500, 3, 2, 1960, "03", 39.701, -84.10, (d, 200_000), "B1"),
        # Above the $1,000 floor but under 10% of the county's value.
        home("NOMINAL", "NB1", 1500, 3, 2, 1960, "03", 39.702, -84.10, (d, 5_000), "B2",
             assessed=180_000),
    )
    body = (await api.get("/v2/parcels/S/comps")).json()
    assert {c["parcel_id"] for c in body["comps"]} == {"C1"}


async def test_multi_parcel_deal_is_not_a_comp(comps_api):
    """A deal's price is recorded on every parcel it covers, so no row is a comp."""
    api, engine = comps_api
    d = dt.date(2026, 6, 1)
    await add(
        engine,
        home("S", "NB1", 1500, 3, 2, 1960, "03", 39.70, -84.10),
        home("C1", "NB1", 1500, 3, 2, 1960, "03", 39.701, -84.10, (d, 200_000), "B1"),
        home("DEAL1", "NB1", 1500, 3, 2, 1960, "03", 39.702, -84.10, (d, 900_000), "FUND"),
        home("DEAL2", "NB9", 3000, 5, 3, 1990, "07", 39.90, -84.30, (d, 900_000), "FUND"),
    )
    body = (await api.get("/v2/parcels/S/comps")).json()
    assert {c["parcel_id"] for c in body["comps"]} == {"C1"}
