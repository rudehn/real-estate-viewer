import csv
import io


async def get(api, path, **params):
    r = await api.get(path, params=params)
    assert r.status_code == 200, r.text
    return r.json()


async def test_first_page_newest_first(api):
    page = await get(api, "/v2/sales", page_size=3)
    assert page["total"] == 9
    assert [r["sale_date"] for r in page["rows"]] == ["2025-09-01", "2025-08-20", "2025-07-01"]
    assert page["applied_filters"] == []


async def test_second_page(api):
    page = await get(api, "/v2/sales", page_size=3, page=2)
    assert len(page["rows"]) == 3 and page["page"] == 2


async def test_sort_by_price_per_sqft_puts_missing_last(api):
    page = await get(api, "/v2/sales", sort="price_per_sqft", order="desc", page_size=20)
    values = [r["price_per_sqft"] for r in page["rows"]]
    known = [v for v in values if v is not None]
    assert known == sorted(known, reverse=True)
    assert values[len(known):] == [None] * (len(values) - len(known))


async def test_filters_are_honored_and_reported(api):
    page = await get(api, "/v2/sales", price_min=100_000, neighborhood="15007000",
                     market_only="true")
    assert [r["sale_price"] for r in page["rows"]] == [150_000]
    assert page["applied_filters"] == ["price_min", "neighborhood"]
    row = page["rows"][0]
    assert (row["neighborhood_name"], row["living_sqft"], row["is_market_sale"]) == (
        "NEWCOM KNOLLS", 1008, True
    )
    assert row["price_per_sqft"] == 150_000 / 1008


async def test_filters_matching_nothing_return_zeros(api):
    page = await get(api, "/v2/sales", price_min=10_000_000)
    assert (page["total"], page["rows"]) == (0, [])


async def test_nominal_transfer_is_not_a_market_sale(api):
    page = await get(api, "/v2/sales", page_size=1)
    assert page["rows"][0]["sale_price"] == 1
    assert page["rows"][0]["is_market_sale"] is False


async def test_csv_export(api):
    r = await api.get("/v2/sales.csv", params={"price_min": 100_000})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert len(rows) == 6
    assert set(rows[0]) >= {"sale_date", "sale_price", "address", "buyer", "seller",
                            "price_per_sqft"}


async def test_flips_exclude_multi_parcel_deals(api):
    page = await get(api, "/v2/sales/flips")
    # R72: bought 2024-03-15 for 300k, sold 2025-08-20 for 330k = +10%.
    assert [(f["parcel_id"], f["buy_price"], f["sell_price"]) for f in page["rows"]] == [
        ("R72 00304 0025", 300_000, 330_000)
    ]


async def test_total_counts_every_matching_row(api):
    for params in ({}, {"market_only": "true"}, {"neighborhood": "15007000"},
                   {"neighborhood": "15007000", "market_only": "true"},
                   {"price_min": 100_000, "sqft_min": 1}):
        page = await get(api, "/v2/sales", page_size=200, **params)
        assert page["total"] == len(page["rows"]), params
