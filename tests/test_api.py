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
    session.add(make_transaction(neighborhood="2020", sale_price=100000))
    session.add(make_transaction(neighborhood="2020", sale_price=100000))
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
