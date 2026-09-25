import datetime as dt

from sqlmodel.ext.asyncio.session import AsyncSession

import derived.mapbinary as mb
from db.models import DataFile


async def test_meta(api):
    r = await api.get("/v2/meta")
    assert r.status_code == 200
    body = r.json()
    assert body["data_version"] == 1
    assert body["latest_sale_date"] == "2025-08-20"
    assert body["parcel_count"] == 5
    assert body["mapped_parcel_count"] == 4
    sales = next(s for s in body["sources"] if s["name"] == "sales")
    assert sales["as_of"] == "2025-08-20"
    assert sales["stale"] is True  # older than 14 days
    assert {"price", "living_sqft", "year_built"} <= set(body["ranges"])


async def test_meta_matches_differently_cased_filenames(api, county_db):
    # The county's own file names are not consistently cased; the ingest
    # scraper's patterns already tolerate that (re.I), so /v2/meta must too.
    async with AsyncSession(county_db) as s:
        s.add(DataFile(
            filename="cama_files_20260831.ZIP", ingested_at=dt.datetime(2026, 8, 31),
        ))
        await s.commit()
    r = await api.get("/v2/meta")
    assert r.status_code == 200
    cama = next(s for s in r.json()["sources"] if s["name"] == "cama")
    assert cama["as_of"] == "2026-08-31"


async def test_map_binary_with_etag(api):
    r = await api.get("/v2/map/parcels.bin")
    assert r.status_code == 200
    assert r.headers["etag"] == '"v1"'
    decoded = mb.decode_map_binary(r.content)
    assert len(decoded["ids"]) == 4
    again = await api.get("/v2/map/parcels.bin", headers={"If-None-Match": '"v1"'})
    assert again.status_code == 304


async def test_map_binary_not_ready(api, tmp_path, monkeypatch):
    monkeypatch.setattr(mb, "DERIVED_DIR", tmp_path / "empty")
    r = await api.get("/v2/map/parcels.bin")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "map_not_ready"


async def test_neighborhood_geojson_has_stats(api):
    r = await api.get("/v2/map/neighborhoods")
    assert r.status_code == 200
    features = {f["properties"]["code"]: f for f in r.json()["features"]}
    butler = features["48150000"]["properties"]
    assert butler["name"] == "N BUTLER TWP"
    assert butler["parcel_count"] == 2
    assert butler["parcels_sold_24m"] == 0
    assert features["48150000"]["geometry"]["type"] in ("Polygon", "MultiPolygon")


def test_today_is_after_fixture_data():
    # The staleness assertion above assumes the fixtures are in the past.
    assert dt.date.today() > dt.date(2025, 9, 3)
