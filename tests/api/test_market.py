import pytest


async def get(api, path, **params):
    r = await api.get(path, params=params)
    assert r.status_code == 200, r.text
    return r.json()


async def test_summary_windows_are_anchored_to_the_data(api):
    body = await get(api, "/v2/market/summary")
    assert body["anchor_date"] == "2025-08-20"
    assert (body["current"]["start"], body["current"]["end"]) == ("2024-08-21", "2025-08-20")
    assert (body["prior"]["start"], body["prior"]["end"]) == ("2023-08-22", "2024-08-20")
    # Current window market sales, single-parcel only: N64 150k, R72 330k.
    assert body["current"]["stats"]["transaction_count"] == 2
    assert body["current"]["stats"]["median_price"] == 240_000
    # Prior window: R72 300k (2024-03-15).
    assert body["prior"]["stats"]["transaction_count"] == 1
    assert body["current"]["label"] == "Aug 2024 - Aug 2025"


async def test_summary_honors_filters(api):
    body = await get(api, "/v2/market/summary", neighborhood="15007000")
    assert body["applied_filters"] == ["neighborhood"]
    assert body["totals"]["transaction_count"] == 2  # N64: 2019 and 2025 market sales


async def test_trends_include_price_per_sqft(api):
    body = await get(api, "/v2/market/trends", granularity="year")
    by_period = {b["period"]: b for b in body["buckets"]}
    assert by_period["2025"]["transaction_count"] == 2
    assert by_period["2025"]["median_price_per_sqft"] == pytest.approx(
        ((150_000 / 1008) + (330_000 / 5103)) / 2
    )


async def test_top_buyers(api):
    body = await get(api, "/v2/market/top-buyers", limit=3)
    assert body["applied_filters"] == []
    assert len(body["rows"]) <= 3


async def test_price_points_cover_the_range(api):
    body = await get(api, "/v2/market/price-points", limit=2)
    assert body["total"] == 6
    assert len(body["points"]) == 2
