import datetime as dt

from sqlmodel.ext.asyncio.session import AsyncSession

from api.cache import cache
from derived.summary import rebuild_derived
from tests.api.conftest import sale


async def search(api, q):
    r = await api.get("/v2/search", params={"q": q})
    assert r.status_code == 200
    return r.json()


async def test_address_prefix(api):
    body = await search(api, "11974 frederick")
    assert [a["parcel_id"] for a in body["addresses"]] == ["A01 00101 0001"]
    assert body["addresses"][0]["neighborhood_name"] == "N BUTLER TWP"


async def test_street_without_house_number(api):
    body = await search(api, "aragon")
    assert [a["address"] for a in body["addresses"]] == ["2301 S ARAGON AVE"]


async def test_parcel_id_with_or_without_spaces(api):
    for q in ("r72 00304", "R7200304"):
        body = await search(api, q)
        assert [p["parcel_id"] for p in body["parcels"]] == ["R72 00304 0025"]


async def test_current_and_past_owners(api):
    body = await search(api, "mullenax")
    assert body["owners"] == [{"name": "MULLENAX SAMANTHA MARIE", "parcel_count": 1}]
    past = await search(api, "fund")
    assert {"name": "FUND LLC", "parcel_count": 0} in past["owners"]


async def test_neighborhoods(api):
    body = await search(api, "butler")
    assert {"code": "48150000", "name": "N BUTLER TWP", "display_name": "N BUTLER TWP"} in (
        body["neighborhoods"]
    )


async def test_search_normalizes_messy_input(api):
    body = await search(api, "  11974   FREDERICK-pike. ")
    assert [a["parcel_id"] for a in body["addresses"]] == ["A01 00101 0001"]
    body = await search(api, "o'neil")
    assert body["owners"] == [] and body["addresses"] == []
    body = await search(api, "%_\\")
    assert body == {"query": "", "addresses": [], "parcels": [], "owners": [],
                    "neighborhoods": []}


async def test_too_short(api):
    body = await search(api, "a")
    assert body["addresses"] == [] and body["owners"] == []


async def test_past_owner_with_punctuation(api, county_db):
    async with AsyncSession(county_db) as s:
        s.add(sale("A01 00101 0001", dt.date(2025, 8, 1), 500_000, buyer="O'DONNELL MARY"))
        await s.commit()
    await rebuild_derived(engine=county_db)
    cache.clear()
    for q in ("o'donnell", "odonnell"):
        body = await search(api, q)
        assert {"name": "O'DONNELL MARY", "parcel_count": 0} in body["owners"]
