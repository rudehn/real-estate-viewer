async def get(api, path, **params):
    r = await api.get(path, params=params)
    assert r.status_code == 200, r.text
    return r.json()


async def test_list(api):
    body = await get(api, "/v2/neighborhoods")
    rows = {r["code"]: r for r in body["rows"]}
    assert set(rows) == {"15007000", "3100WALK", "48150000"}
    assert (rows["15007000"]["sales"], rows["15007000"]["median_price"]) == (2, 120_000)
    assert rows["15007000"]["name"] == "NEWCOM KNOLLS"
    assert rows["48150000"]["sales"] == 1  # the two-parcel deal is excluded
    assert rows["48150000"]["parcel_count"] == 2


async def test_list_honors_date_filter(api):
    body = await get(api, "/v2/neighborhoods", date_from="2025-01-01")
    assert body["applied_filters"] == ["date_from"]
    assert {r["code"]: r["sales"] for r in body["rows"]} == {"15007000": 1, "3100WALK": 1}


async def test_trends(api):
    body = await get(api, "/v2/neighborhoods/trends", min_sales=1)
    assert {"neighborhood": "15007000", "name": "NEWCOM KNOLLS", "year": 2019, "sales": 1,
            "median_price": 90_000} in body["rows"]


async def test_report(api):
    body = await get(api, "/v2/neighborhoods/48150000")
    assert (body["name"], body["tax_district"]["code"]) == ("N BUTLER TWP", "A01")
    assert body["summary"]["parcel_count"] == 2
    assert body["trend"] == [{"year": 2023, "sales": 1, "median_price": 320_000,
                              "median_price_per_sqft": 320_000 / 2464}]
    assert [s["sale_price"] for s in body["recent_sales"]] == [320_000]


async def test_unknown_neighborhood_is_404(api):
    r = await api.get("/v2/neighborhoods/NOPE")
    assert r.status_code == 404
