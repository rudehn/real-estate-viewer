"""
Integration tests for FastAPI endpoints.
Uses an in-memory SQLite database via the session fixture in conftest.py.
"""
import datetime

import pytest

from db.models import Parcel, ParcelClass, Transaction


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_parcel(**kwargs) -> Parcel:
    defaults = dict(
        parcel_id="P001",
        parcel_location="123 MAIN ST",
        parcel_class=ParcelClass.R,
        acres=0.25,
    )
    return Parcel(**{**defaults, **kwargs})


def make_transaction(**kwargs) -> Transaction:
    defaults = dict(
        parcel_id="P001",
        sale_date=datetime.date(2023, 6, 1),
        sale_price=200000.0,
        old_owner="SELLER A",
        new_owner="BUYER B",
        parcel_location="123 MAIN ST",
        mailing_name="BUYER B",
        mailing_address="123 MAIN ST",
        parcel_class=ParcelClass.R,
        acres=0.25,
        taxable_land=10000,
        taxable_building=40000,
        taxable_total=50000,
        neighborhood="1010",
    )
    return Transaction(**{**defaults, **kwargs})


# ---------------------------------------------------------------------------
# /transactions
# ---------------------------------------------------------------------------

async def test_transactions_empty_db(client):
    response = await client.get("/transactions")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0
    assert data["entities"] == []


async def test_transactions_returns_inserted_record(client, session):
    parcel = make_parcel()
    txn = make_transaction()
    session.add(parcel)
    session.add(txn)
    await session.commit()

    response = await client.get("/transactions")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["entities"][0]["sale_price"] == 200000.0


async def test_transactions_filter_by_parcel_class(client, session):
    parcel_r = make_parcel(parcel_id="P001", parcel_class=ParcelClass.R)
    parcel_c = make_parcel(parcel_id="P002", parcel_location="456 OAK ST", parcel_class=ParcelClass.C)
    txn_r = make_transaction(parcel_id="P001", parcel_class=ParcelClass.R)
    txn_c = make_transaction(parcel_id="P002", parcel_class=ParcelClass.C)
    session.add_all([parcel_r, parcel_c, txn_r, txn_c])
    await session.commit()

    response = await client.get("/transactions?parcel_class__in=Residential")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["entities"][0]["parcel_class"] == "Residential"


# ---------------------------------------------------------------------------
# /parcels
# ---------------------------------------------------------------------------

async def test_parcels_empty_db(client):
    response = await client.get("/parcels")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0
    assert data["entities"] == []


# ---------------------------------------------------------------------------
# /analytics/top-buyers
# ---------------------------------------------------------------------------

async def test_top_buyers_empty_db(client):
    response = await client.get("/analytics/top-buyers")
    assert response.status_code == 200
    assert response.json() == []


async def test_top_buyers_returns_ranked_results(client, session):
    parcel = make_parcel()
    session.add(parcel)
    # BUYER B buys twice, BUYER C buys once
    session.add(make_transaction(new_owner="BUYER B", sale_price=100000))
    session.add(make_transaction(new_owner="BUYER B", sale_price=150000))
    session.add(make_transaction(new_owner="BUYER C", sale_price=200000))
    await session.commit()

    response = await client.get("/analytics/top-buyers?limit=5")
    assert response.status_code == 200
    results = response.json()
    assert results[0]["owner_name"] == "BUYER B"
    assert results[0]["transaction_count"] == 2


# ---------------------------------------------------------------------------
# /analytics/top-sellers
# ---------------------------------------------------------------------------

async def test_top_sellers_empty_db(client):
    response = await client.get("/analytics/top-sellers")
    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# /analytics/neighborhoods
# ---------------------------------------------------------------------------

async def test_neighborhoods_empty_db(client):
    response = await client.get("/analytics/neighborhoods")
    assert response.status_code == 200
    assert response.json() == []


async def test_neighborhoods_groups_correctly(client, session):
    parcel_a = make_parcel(parcel_id="P001")
    parcel_b = make_parcel(parcel_id="P002", parcel_location="456 OAK ST")
    session.add_all([parcel_a, parcel_b])
    # Neighborhood 1010: 2 transactions; neighborhood 2020: 1 transaction
    session.add(make_transaction(parcel_id="P001", neighborhood="1010", sale_price=100000))
    session.add(make_transaction(parcel_id="P002", neighborhood="1010", sale_price=200000))
    session.add(make_transaction(parcel_id="P001", neighborhood="2020", sale_price=50000))
    await session.commit()

    response = await client.get("/analytics/neighborhoods")
    assert response.status_code == 200
    results = response.json()

    # Should be sorted by transaction_count desc
    assert results[0]["neighborhood"] == "1010"
    assert results[0]["transaction_count"] == 2
    assert results[0]["total_volume"] == 300000.0
    assert results[1]["neighborhood"] == "2020"


async def test_neighborhoods_min_transactions_filter(client, session):
    parcel = make_parcel()
    session.add(parcel)
    session.add(make_transaction(neighborhood="1010", sale_price=100000))
    session.add(make_transaction(neighborhood="2020", sale_price=120000))
    session.add(make_transaction(neighborhood="2020", sale_price=150000))
    await session.commit()

    response = await client.get("/analytics/neighborhoods?min_transactions=2")
    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert results[0]["neighborhood"] == "2020"


# ---------------------------------------------------------------------------
# /parcels/{parcel_id}/history
# ---------------------------------------------------------------------------

async def test_parcel_history_unknown_parcel(client):
    response = await client.get("/parcels/UNKNOWN/history")
    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# /analytics/market-stats
# ---------------------------------------------------------------------------

async def test_market_stats_empty_db(client):
    response = await client.get("/analytics/market-stats")
    assert response.status_code == 200
    assert response.json() == []


async def test_market_stats_median_odd_and_even(client, session):
    session.add(make_parcel())
    # 2022: three sales -> median is the middle value
    for price in (100_000, 200_000, 900_000):
        session.add(make_transaction(sale_date=datetime.date(2022, 5, 1), sale_price=price))
    # 2023: four sales -> median is the average of the two middle values
    for price in (100_000, 200_000, 300_000, 900_000):
        session.add(make_transaction(sale_date=datetime.date(2023, 5, 1), sale_price=price))
    await session.commit()

    response = await client.get("/analytics/market-stats?granularity=year")
    assert response.status_code == 200
    buckets = {b["period"]: b for b in response.json()}
    assert buckets["2022"]["median_price"] == 200_000
    assert buckets["2022"]["transaction_count"] == 3
    assert buckets["2022"]["total_volume"] == 1_200_000
    assert buckets["2023"]["median_price"] == 250_000
    assert buckets["2023"]["transaction_count"] == 4


async def test_market_stats_excludes_non_market_sales(client, session):
    session.add(make_parcel())
    session.add(make_transaction(sale_price=200_000))
    # Nominal transfer and county-flagged non-market sale must not count
    session.add(make_transaction(sale_price=0))
    session.add(make_transaction(sale_price=150_000, sale_validity="RELATED INDIVIDUALS OR CORPORATIONS"))
    # Multi-parcel sales carry the whole deal price on each row; excluded from stats
    session.add(make_transaction(sale_price=800_000, sale_validity="VALID MULTI-PCL SALE"))
    # Unflagged portfolio deal: same buyer/date/price on several parcels
    for i in range(3):
        session.add(make_transaction(
            parcel_id=f"D00{i + 1}", new_owner="PORTFOLIO LLC",
            sale_price=41_000_000, sale_validity="VALID SALE",
        ))
    await session.commit()

    response = await client.get("/analytics/market-stats")
    buckets = response.json()
    assert len(buckets) == 1
    assert buckets[0]["transaction_count"] == 1
    assert buckets[0]["median_price"] == 200_000

    # market_only=false keeps everything with a nonzero price
    response = await client.get("/analytics/market-stats?market_only=false")
    assert response.json()[0]["transaction_count"] == 3


async def test_market_stats_granularity_labels(client, session):
    session.add(make_parcel())
    session.add(make_transaction(sale_date=datetime.date(2023, 8, 15), sale_price=100_000))
    await session.commit()

    monthly = (await client.get("/analytics/market-stats?granularity=month")).json()
    quarterly = (await client.get("/analytics/market-stats?granularity=quarter")).json()
    assert monthly[0]["period"] == "2023-08"
    assert monthly[0]["period_start"] == "2023-08-01"
    assert quarterly[0]["period"] == "2023-Q3"
    assert quarterly[0]["period_start"] == "2023-07-01"


async def test_market_stats_respects_transaction_filters(client, session):
    session.add(make_parcel())
    session.add(make_transaction(sale_price=100_000, parcel_class=ParcelClass.R))
    session.add(make_transaction(sale_price=500_000, parcel_class=ParcelClass.C))
    await session.commit()

    response = await client.get("/analytics/market-stats?parcel_class__in=Residential")
    buckets = response.json()
    assert buckets[0]["transaction_count"] == 1
    assert buckets[0]["median_price"] == 100_000


# ---------------------------------------------------------------------------
# /analytics/distressed
# ---------------------------------------------------------------------------

async def test_distressed_excludes_nominal_transfers(client, session):
    session.add(make_parcel())
    # $0 family transfer on a $100k-assessed house: not a distressed sale
    session.add(make_transaction(sale_price=0, assessed_total=100_000))
    # Real foreclosure sale at half of assessed: must appear
    session.add(make_transaction(
        sale_price=50_000, assessed_total=100_000,
        sale_validity="LIQUIDATION/FORECLOSURE",
    ))
    await session.commit()

    response = await client.get("/analytics/distressed")
    results = response.json()
    assert len(results) == 1
    assert results[0]["sale_price"] == 50_000


# ---------------------------------------------------------------------------
# /analytics/acquisition-waves
# ---------------------------------------------------------------------------

async def test_acquisition_waves_counts_same_day_buys_once(client, session):
    session.add(make_parcel())
    # 5 same-day purchases of different parcels at individual prices:
    # the count must be 5, not 5x5=25
    for i in range(5):
        session.add(make_transaction(
            parcel_id=f"P00{i + 1}",
            new_owner="BULK BUYER LLC",
            sale_date=datetime.date(2023, 6, 1),
            sale_price=100_000 + i * 1_000,
        ))
    await session.commit()

    response = await client.get("/analytics/acquisition-waves?min_acquisitions=5")
    results = response.json()
    assert len(results) == 1
    assert results[0]["owner_name"] == "BULK BUYER LLC"
    assert results[0]["acquisition_count"] == 5
    assert results[0]["total_spent"] == 510_000


async def test_acquisition_waves_portfolio_deal_price_counted_once(client, session):
    session.add(make_parcel())
    # A 5-parcel portfolio deal stamps the full $1M deal price on every row:
    # 5 acquisitions, but $1M spent — not $5M.
    for i in range(5):
        session.add(make_transaction(
            parcel_id=f"P00{i + 1}",
            new_owner="PORTFOLIO BUYER LLC",
            sale_date=datetime.date(2023, 6, 1),
            sale_price=1_000_000,
        ))
    await session.commit()

    response = await client.get("/analytics/acquisition-waves?min_acquisitions=5")
    results = response.json()
    assert results[0]["acquisition_count"] == 5
    assert results[0]["total_spent"] == 1_000_000


async def test_acquisition_waves_one_window_per_owner(client, session):
    session.add(make_parcel())
    # Purchases spread over three days inside one 90-day window: without
    # dedup each start date would produce its own overlapping-window row.
    for day in (1, 2, 3, 4, 5):
        session.add(make_transaction(
            new_owner="SPREE LLC",
            sale_date=datetime.date(2023, 6, day),
            sale_price=100_000,
        ))
    await session.commit()

    response = await client.get("/analytics/acquisition-waves?min_acquisitions=2")
    results = response.json()
    owners = [r["owner_name"] for r in results]
    assert owners.count("SPREE LLC") == 1
    # The biggest window starts at the earliest purchase and covers all 5
    assert results[0]["acquisition_count"] == 5


# ---------------------------------------------------------------------------
# /analytics/flips and /analytics/stale-parcels (SQLite date arithmetic)
# ---------------------------------------------------------------------------

async def test_flips_hold_days_computed_correctly(client, session):
    session.add(make_parcel())
    # Real flip: bought then resold 152 days later at +100%
    session.add(make_transaction(sale_date=datetime.date(2020, 1, 1), sale_price=100_000, new_owner="FLIPPER"))
    session.add(make_transaction(sale_date=datetime.date(2020, 6, 1), sale_price=200_000, old_owner="FLIPPER"))
    await session.commit()

    response = await client.get("/analytics/flips")
    results = response.json()
    assert len(results) == 1
    assert results[0]["hold_days"] == 152
    assert results[0]["profit"] == 100_000


async def test_flips_excludes_long_holds_and_nominal_buys(client, session):
    session.add(make_parcel())
    # 5-year hold: not a flip (naive text math would call this 5 "days")
    session.add(make_transaction(sale_date=datetime.date(2012, 5, 14), sale_price=100_000))
    session.add(make_transaction(sale_date=datetime.date(2017, 10, 25), sale_price=200_000))
    # $2 nominal "buy" resold high: not a flip either
    session.add(make_transaction(parcel_id="P001", sale_date=datetime.date(2020, 1, 1), sale_price=2))
    session.add(make_transaction(parcel_id="P001", sale_date=datetime.date(2020, 3, 1), sale_price=1_325_000))
    await session.commit()

    response = await client.get("/analytics/flips")
    assert response.json() == []


async def test_stale_parcels_age_computed_correctly(client, session):
    session.add(make_parcel())
    session.add(make_transaction(sale_date=datetime.date(2010, 1, 1), sale_price=100_000))
    await session.commit()

    response = await client.get("/analytics/stale-parcels?min_years=10")
    results = response.json()
    assert len(results) == 1
    # Sold Jan 2010, so 16+ years ago as of 2026
    assert results[0]["years_since_sale"] > 15


# ---------------------------------------------------------------------------
# /analytics/owner-profile
# ---------------------------------------------------------------------------

async def test_owner_profile_activity_and_holds(client, session):
    session.add(make_parcel())
    # Bought P001 in 2020, sold it in 2021 (365-day hold)
    session.add(make_transaction(
        parcel_id="P001", new_owner="INVESTOR LLC",
        sale_date=datetime.date(2020, 3, 1), sale_price=100_000,
    ))
    session.add(make_transaction(
        parcel_id="P001", old_owner="INVESTOR LLC", new_owner="FAMILY HOME BUYER",
        sale_date=datetime.date(2021, 3, 1), sale_price=150_000,
    ))
    await session.commit()

    response = await client.get("/analytics/owner-profile?owner_name=INVESTOR%20LLC")
    assert response.status_code == 200
    profile = response.json()
    assert profile["total_buys"] == 1
    assert profile["total_sells"] == 1
    assert profile["median_hold_days"] == 365
    years = {a["year"]: a for a in profile["activity"]}
    assert years[2020]["buy_count"] == 1
    assert years[2020]["total_spent"] == 100_000
    assert years[2021]["sell_count"] == 1
    assert years[2021]["total_received"] == 150_000


async def test_owner_profile_portfolio_deal_spent_once(client, session):
    session.add(make_parcel())
    # 3-parcel portfolio buy: $900k stamped on each row, spent must be $900k
    for i in range(3):
        session.add(make_transaction(
            parcel_id=f"P00{i + 1}", new_owner="PORTFOLIO LLC",
            sale_date=datetime.date(2022, 5, 1), sale_price=900_000,
        ))
    await session.commit()

    profile = (await client.get("/analytics/owner-profile?owner_name=PORTFOLIO%20LLC")).json()
    years = {a["year"]: a for a in profile["activity"]}
    assert years[2022]["buy_count"] == 3
    assert years[2022]["total_spent"] == 900_000


async def test_owner_profile_related_by_mailing_address(client, session):
    session.add(make_parcel())
    session.add(make_transaction(
        parcel_id="P001", new_owner="VB ONE LLC",
        mailing_address="PO BOX 123 DAYTON OH", sale_price=100_000,
    ))
    session.add(make_transaction(
        parcel_id="P002", new_owner="VB ELEVEN LLC",
        mailing_address="PO BOX 123 DAYTON OH", sale_price=120_000,
    ))
    session.add(make_transaction(
        parcel_id="P003", new_owner="UNRELATED CO",
        mailing_address="99 ELSEWHERE ST", sale_price=90_000,
    ))
    await session.commit()

    profile = (await client.get("/analytics/owner-profile?owner_name=VB%20ONE%20LLC")).json()
    related_names = [r["owner_name"] for r in profile["related_owners"]]
    assert related_names == ["VB ELEVEN LLC"]
    assert profile["related_owners"][0]["shared_address"] == "PO BOX 123 DAYTON OH"


# ---------------------------------------------------------------------------
# /parcels/{parcel_id}/comps
# ---------------------------------------------------------------------------

async def test_parcel_comps_same_neighborhood_and_class(client, session):
    session.add(make_parcel())
    today = datetime.date.today()
    # The subject parcel
    session.add(make_transaction(parcel_id="P001", neighborhood="1010", sale_price=100_000))
    # Two recent comps in the same neighborhood
    session.add(make_transaction(
        parcel_id="C001", neighborhood="1010", sale_price=200_000,
        sale_date=today - datetime.timedelta(days=30),
    ))
    session.add(make_transaction(
        parcel_id="C002", neighborhood="1010", sale_price=300_000,
        sale_date=today - datetime.timedelta(days=60),
    ))
    # Wrong neighborhood and a nominal transfer: not comps
    session.add(make_transaction(
        parcel_id="C003", neighborhood="9999", sale_price=999_000,
        sale_date=today - datetime.timedelta(days=30),
    ))
    session.add(make_transaction(
        parcel_id="C004", neighborhood="1010", sale_price=0,
        sale_date=today - datetime.timedelta(days=10),
    ))
    await session.commit()

    response = await client.get("/parcels/P001/comps")
    assert response.status_code == 200
    result = response.json()
    assert result["neighborhood"] == "1010"
    assert {c["parcel_id"] for c in result["comps"]} == {"C001", "C002"}
    assert result["median_price"] == 250_000


async def test_parcel_comps_unknown_parcel(client):
    response = await client.get("/parcels/NOPE/comps")
    assert response.status_code == 200
    assert response.json()["comps"] == []


# ---------------------------------------------------------------------------
# /health/data
# ---------------------------------------------------------------------------

async def test_data_health(client, session):
    session.add(make_parcel(latitude=39.7, longitude=-84.2))
    session.add(make_parcel(parcel_id="P002", parcel_location="456 OAK ST"))
    session.add(make_transaction(sale_price=200_000))
    session.add(make_transaction(parcel_id="P002", sale_price=0))
    await session.commit()

    response = await client.get("/health/data")
    assert response.status_code == 200
    health = response.json()
    assert health["total_transactions"] == 2
    assert health["total_parcels"] == 2
    assert health["geocoded_pct"] == 50.0
    assert health["market_sale_pct"] == 50.0
    assert health["latest_sale_date"] == "2023-06-01"


# ---------------------------------------------------------------------------
# market_only on top-buyers
# ---------------------------------------------------------------------------

async def test_top_buyers_market_only_excludes_nominal(client, session):
    session.add(make_parcel())
    session.add(make_transaction(new_owner="REAL BUYER", sale_price=250_000))
    for i in range(3):
        session.add(make_transaction(
            parcel_id=f"Q00{i + 1}", new_owner="QUITCLAIM CO", sale_price=0,
        ))
    await session.commit()

    market = (await client.get("/analytics/top-buyers")).json()
    assert [r["owner_name"] for r in market] == ["REAL BUYER"]

    raw = (await client.get("/analytics/top-buyers?market_only=false")).json()
    assert raw[0]["owner_name"] == "QUITCLAIM CO"
