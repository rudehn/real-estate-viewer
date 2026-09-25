import datetime as dt
from pathlib import Path

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from db.county_models import NeighborhoodSummary, ParcelSummary
from db.models import Parcel, ParcelClass, Transaction
from derived.summary import current_data_version, latest_sale_date, rebuild_derived
from ingest.cama_ingest import ingest_cama
from ingest.taxroll_ingest import ingest_taxroll

FIXTURES = Path(__file__).parent.parent / "fixtures" / "county"


@pytest.fixture(autouse=True)
def derived_dir(tmp_path, monkeypatch):
    import derived.mapbinary as mb

    monkeypatch.setattr(mb, "DERIVED_DIR", tmp_path / "derived")


def sale(parcel_id, day, price, buyer="BUYER A", seller="SELLER B", validity="VALID SALE"):
    return Transaction(
        parcel_id=parcel_id, sale_date=day, sale_price=price, old_owner=seller, new_owner=buyer,
        parcel_location="X", mailing_name=buyer, mailing_address="X",
        parcel_class=ParcelClass.R, acres=0.1, taxable_land=0, taxable_building=0,
        taxable_total=0, sale_validity=validity,
    )


@pytest.fixture
async def loaded(db_engine):
    async with AsyncSession(db_engine) as s:
        s.add(Parcel(parcel_id="Z99 99999 9999", parcel_location="1 GONE ST",
                     parcel_class=ParcelClass.R, acres=0.1))
        await s.commit()
    await ingest_cama(FIXTURES / "cama_fixture.zip", engine=db_engine)
    await ingest_taxroll(FIXTURES / "TAXROLL_20260923.zip", engine=db_engine)
    async with AsyncSession(db_engine) as s:
        s.add_all([
            sale("N64 00101 0003", dt.date(2019, 5, 1), 90_000),
            sale("N64 00101 0003", dt.date(2025, 6, 1), 150_000),
            # A later nominal transfer is not a market sale.
            sale("N64 00101 0003", dt.date(2025, 9, 1), 1, buyer="HEIR C"),
            # One deal covering two parcels: not a per-parcel price.
            sale("A01 00101 0001", dt.date(2025, 7, 1), 900_000, buyer="FUND LLC"),
            sale("A01 00102 0069", dt.date(2025, 7, 1), 900_000, buyer="FUND LLC"),
            sale("Z99 99999 9999", dt.date(2010, 1, 1), 50_000),
        ])
        await s.commit()
    return db_engine


async def summary(engine, parcel_id):
    async with AsyncSession(engine) as s:
        return await s.get(ParcelSummary, parcel_id)


async def test_last_market_sale_and_price_per_sqft(loaded):
    await rebuild_derived(engine=loaded)
    ranch = await summary(loaded, "N64 00101 0003")
    assert (ranch.last_sale_date, ranch.last_sale_price) == (dt.date(2025, 6, 1), 150_000)
    assert ranch.price_per_sqft == pytest.approx(150_000 / 1008)
    assert (ranch.living_sqft, ranch.beds, ranch.baths, ranch.year_built) == (1008, 3, 1.0, 1955)
    assert ranch.value_change_pct == pytest.approx(18.699, abs=1e-3)
    assert ranch.market_value == 148_670


async def test_multi_parcel_deal_is_not_a_last_sale(loaded):
    await rebuild_derived(engine=loaded)
    rural = await summary(loaded, "A01 00101 0001")
    assert rural.last_sale_price is None
    assert rural.price_per_sqft is None


async def test_summary_sums_multiple_dwellings(loaded):
    await rebuild_derived(engine=loaded)
    two = await summary(loaded, "A01 00102 0069")
    assert (two.living_sqft, two.beds, two.baths) == (2490, 5, 2.5)
    assert two.year_built == 1985  # from the larger card


async def test_search_keys_owner_and_tax(loaded):
    await rebuild_derived(engine=loaded)
    rural = await summary(loaded, "A01 00101 0001")
    assert rural.address == "11974 FREDERICK PIKE"
    assert (rural.address_search, rural.street_search) == ("11974 FREDERICK PIKE", "FREDERICK PIKE")
    assert rural.parcel_id_search == "A01001010001"
    assert (rural.owner_name, rural.owner_search) == (
        "MULLENAX SAMANTHA MARIE", "MULLENAX SAMANTHA MARIE"
    )
    assert (rural.occupancy, rural.annual_tax) == ("owner_occupied", pytest.approx(6066.22))
    assert rural.year_built_is_placeholder is True
    assert rural.latitude == pytest.approx(39.92128, abs=1e-4)


async def test_inactive_parcel_without_cama_data_still_summarized(loaded):
    await rebuild_derived(engine=loaded)
    gone = await summary(loaded, "Z99 99999 9999")
    assert gone.is_active is False
    assert gone.last_sale_price == 50_000
    assert gone.living_sqft is None


async def test_neighborhood_summary(loaded):
    await rebuild_derived(engine=loaded)
    async with AsyncSession(loaded) as s:
        butler = await s.get(NeighborhoodSummary, "48150000")
    assert (butler.parcel_count, butler.residential_count) == (2, 2)
    assert butler.median_year_built == pytest.approx((1919 + 1985) / 2)


async def test_latest_sale_date_is_the_newest_market_row(loaded):
    async with loaded.connect() as conn:
        assert await latest_sale_date(conn) == dt.date(2025, 7, 1)


async def test_neighborhood_summary_recent_sales(loaded):
    await rebuild_derived(engine=loaded)
    async with AsyncSession(loaded) as s:
        ranch_neighborhood = await s.get(NeighborhoodSummary, "15007000")
    assert ranch_neighborhood.sales_24m == 1
    assert ranch_neighborhood.median_sale_price_24m == 150_000
    assert ranch_neighborhood.median_price_per_sqft_24m == pytest.approx(150_000 / 1008)


async def test_data_version_increments(loaded):
    async with loaded.connect() as conn:
        assert await current_data_version(conn) == 0
    assert await rebuild_derived(engine=loaded) == 1
    assert await rebuild_derived(engine=loaded) == 2


async def test_rebuild_writes_map_binary(loaded, tmp_path):
    import derived.mapbinary as mb

    version = await rebuild_derived(engine=loaded)
    latest_version, path = mb.latest_map_binary()
    decoded = mb.decode_map_binary(path.read_bytes())
    assert latest_version == version
    # Active parcels with coordinates only: the four CAMA parcels.
    assert decoded["ids"] == [
        "A01 00101 0001", "A01 00102 0069", "N64 00101 0003", "R72 00304 0025"
    ]
