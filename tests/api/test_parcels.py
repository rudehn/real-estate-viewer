import pytest


async def test_full_profile(api):
    r = await api.get("/v2/parcels/A01 00101 0001")
    assert r.status_code == 200
    p = r.json()
    assert (p["address"], p["is_active"], p["parcel_class"]) == ("11974 FREDERICK PIKE", True, "R")
    assert p["neighborhood"] == {"code": "48150000", "name": "N BUTLER TWP",
                                 "display_name": "N BUTLER TWP"}
    assert p["tax_district"]["code"] == "A01"
    facts = p["facts"]
    assert (facts["living_sqft"], facts["beds"], facts["baths"]) == (2464, 3, 1.0)
    assert (facts["style"], facts["year_built"], facts["year_built_is_placeholder"]) == (
        "OLD STYLE", 1919, True
    )
    assert (facts["detached_garage_sqft"], facts["basement_garage_cars"]) == (768, 1)
    assert p["lot"]["lot_acres"] == pytest.approx(2.0)
    assert p["dwellings"][0]["sketch"][0]["vector"] == "A0CU20R45D20L45"
    assert {f["code"] for f in p["features"]} == {"RG1", "AL1"}
    value = p["value"]
    assert (value["market_value_2025"], value["market_value_2026"]) == (274320, 267560)
    # The 2025 two-parcel deal is not a per-parcel price, so the 2023 sale is the last sale.
    assert (value["last_sale_date"], value["last_sale_price"]) == ("2023-03-20", 320_000)
    tax = p["tax"]
    assert tax["annual_bill"] == pytest.approx(6066.22)
    assert tax["effective_rate_pct"] == pytest.approx(6066.22 / 274320 * 100, abs=1e-3)
    assert p["owner"]["name"] == "MULLENAX SAMANTHA MARIE"
    assert p["owner"]["occupancy"] == "owner_occupied"
    assert "owner_occupied" in p["badges"]


async def test_price_per_sqft_vs_neighborhood(api):
    p = (await api.get("/v2/parcels/N64 00101 0003")).json()
    assert p["value"]["last_sale_price"] == 150_000
    assert p["value"]["price_per_sqft"] == pytest.approx(150_000 / 1008)
    assert p["value"]["ratio_to_last_sale"] == pytest.approx(148_670 / 150_000)


async def test_profile_of_inactive_parcel_without_cama_data(api):
    r = await api.get("/v2/parcels/Z99 99999 9999")
    assert r.status_code == 200
    p = r.json()
    assert p["is_active"] is False
    assert p["facts"] is None and p["dwellings"] == [] and p["tax"] is None
    assert "retired_parcel" in p["badges"]
    assert p["value"]["last_sale_price"] == 50_000


async def test_unknown_parcel_is_404(api):
    r = await api.get("/v2/parcels/NOPE")
    assert r.status_code == 404
    assert r.json() == {"error": {"code": "not_found", "message": "Parcel NOPE not found"}}


async def test_timeline(api):
    events = (await api.get("/v2/parcels/N64 00101 0003/timeline")).json()
    kinds = [(e["date"], e["kind"], e["title"]) for e in events]
    assert kinds == [
        ("2026-01-01", "reappraisal", "2026 reappraisal"),
        ("2025-09-01", "sale", "Transferred"),
        ("2025-06-01", "sale", "Sold"),
        ("2019-05-01", "sale", "Sold"),
        ("1955-01-01", "built", "Built"),
    ]
    sold = events[2]
    assert (sold["amount"], sold["detail"]["buyer"], sold["detail"]["is_market_sale"]) == (
        150_000, "JONES MARY", True
    )
    assert events[0]["detail"]["change_pct"] == pytest.approx(18.699, abs=1e-3)


async def test_placeholder_year_is_labeled(api):
    events = (await api.get("/v2/parcels/A01 00101 0001/timeline")).json()
    built = next(e for e in events if e["kind"] == "built")
    assert built["title"] == "Built before 1920"
