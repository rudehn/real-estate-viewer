import datetime as dt

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from db.county_models import Dwelling, ParcelSummary
from db.maintenance import repair_schema
from db.models import Parcel, ParcelClass


async def test_new_tables_exist(db_engine):
    async with db_engine.connect() as conn:
        tables = await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
    assert {
        "parcel_detail", "dwelling", "parcel_feature", "parcel_value", "neighborhood",
        "tax_district", "parcel_tax", "parcel_summary", "neighborhood_summary", "data_version",
    } <= tables


async def test_parcel_defaults(session):
    session.add(Parcel(parcel_id="P1", parcel_location="1 MAIN ST",
                       parcel_class=ParcelClass.R, acres=0.1))
    await session.commit()
    parcel = await session.get(Parcel, "P1")
    assert parcel.is_active is True
    assert parcel.neighborhood is None


async def test_dwelling_primary_key_is_parcel_and_card(session):
    for card in (1, 2):
        session.add(Dwelling(parcel_id="P1", card=card, living_sqft=1000,
                             snapshot_date=dt.date(2026, 8, 31)))
    await session.commit()
    assert await session.get(Dwelling, ("P1", 2)) is not None


async def test_summary_defaults(session):
    session.add(ParcelSummary(parcel_id="P1", parcel_class="R", is_active=True,
                              occupancy="unknown"))
    await session.commit()
    row = await session.get(ParcelSummary, "P1")
    assert (row.distress_score, row.distress_flags, row.permit_count_5y) == (0, 0, 0)


async def test_repair_adds_new_parcel_columns_to_an_old_database(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/old.db")
    async with engine.begin() as conn:
        await conn.execute(text(
            "CREATE TABLE parcel (parcel_id VARCHAR PRIMARY KEY, parcel_location VARCHAR NOT NULL,"
            " parcel_class VARCHAR(1) NOT NULL, acres FLOAT NOT NULL, latitude FLOAT,"
            " longitude FLOAT)"
        ))
        await conn.execute(text(
            "INSERT INTO parcel VALUES ('P1', '1 MAIN ST', 'R', 0.1, NULL, NULL)"
        ))
        await conn.run_sync(repair_schema)
        await conn.run_sync(repair_schema)  # idempotent
        columns = await conn.run_sync(
            lambda c: {col["name"] for col in inspect(c).get_columns("parcel")}
        )
        active = (await conn.execute(text("SELECT is_active FROM parcel"))).scalar_one()
    await engine.dispose()
    assert {"neighborhood", "tax_district", "land_use_code", "zip", "census_tract",
            "is_active", "coord_source"} <= columns
    assert bool(active) is True
