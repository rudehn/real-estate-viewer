import zipfile
from pathlib import Path

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from county.fixedwidth import TooManyBadRows
from db.county_models import ParcelDetail
from db.models import Parcel, ParcelClass
from ingest.cama_ingest import compose_address, ingest_cama

FIXTURE = Path(__file__).parent.parent / "fixtures" / "county" / "cama_fixture.zip"


async def seed(db_engine):
    async with AsyncSession(db_engine) as s:
        s.add(Parcel(parcel_id="A01 00102 0069", parcel_location="920 ANTIOCH SCHOOL RD",
                     parcel_class=ParcelClass.R, acres=0.0, latitude=0.0))
        s.add(Parcel(parcel_id="R72 00304 0025", parcel_location="208 W MONUMENT AVE",
                     parcel_class=ParcelClass.R, acres=0.343,
                     latitude=39.763072, longitude=-84.196600))
        s.add(Parcel(parcel_id="Z99 99999 9999", parcel_location="1 GONE ST",
                     parcel_class=ParcelClass.R, acres=0.1,
                     latitude=39.7, longitude=-84.2))
        await s.commit()


async def get(db_engine, model, key):
    async with AsyncSession(db_engine) as s:
        return await s.get(model, key)


def test_compose_address():
    assert compose_address(2301, "S", "ARAGON", "AVE", None) == "2301 S ARAGON AVE"
    assert compose_address(None, None, "GLENDALE", "AVE", None) == "GLENDALE AVE"
    assert compose_address(0, None, "MAIN", "ST", "APT 4") == "MAIN ST APT 4"


async def test_new_parcels_are_inserted_with_county_data(db_engine):
    await seed(db_engine)
    counts = await ingest_cama(FIXTURE, engine=db_engine)
    assert counts["parcel"] == 4
    p = await get(db_engine, Parcel, "A01 00101 0001")
    assert p.parcel_location == "11974 FREDERICK PIKE"
    assert p.parcel_class == ParcelClass.R
    assert p.acres == pytest.approx(2.0)
    assert (p.neighborhood, p.tax_district, p.land_use_code, p.zip) == (
        "48150000", "A01", "511", "45377"
    )
    assert p.latitude == pytest.approx(39.92128, abs=1e-4)
    assert p.longitude == pytest.approx(-84.27433, abs=1e-4)
    assert (p.coord_source, p.is_active) == ("county", True)


async def test_county_coordinates_replace_the_failed_geocode_sentinel(db_engine):
    await seed(db_engine)
    await ingest_cama(FIXTURE, engine=db_engine)
    p = await get(db_engine, Parcel, "A01 00102 0069")
    assert p.latitude != 0.0
    assert p.coord_source == "county"
    # Existing parcels keep the location string that sales history uses.
    assert p.parcel_location == "920 ANTIOCH SCHOOL RD"


async def test_parcels_missing_from_cama_are_marked_inactive(db_engine):
    await seed(db_engine)
    await ingest_cama(FIXTURE, engine=db_engine)
    gone = await get(db_engine, Parcel, "Z99 99999 9999")
    assert gone.is_active is False
    assert gone.coord_source == "census"  # it kept its geocoded location


async def test_parcel_details(db_engine):
    await ingest_cama(FIXTURE, engine=db_engine)
    d = await get(db_engine, ParcelDetail, "N64 00101 0003")
    assert (d.house_number, d.street_direction, d.street_name, d.street_suffix) == (
        2301, "S", "ARAGON", "AVE"
    )
    assert d.land_use.startswith("R - ")
    assert (d.city, d.zip, d.living_units) == ("DAYTON", "45420", 1)
    rural = await get(db_engine, ParcelDetail, "A01 00101 0001")
    assert rural.lot_acres == pytest.approx(2.0)
    assert rural.lot_sqft == 12632 + 30928 + 43560


async def test_ingest_is_idempotent(db_engine):
    await ingest_cama(FIXTURE, engine=db_engine)
    await ingest_cama(FIXTURE, engine=db_engine)
    async with AsyncSession(db_engine) as s:
        parcels = (await s.exec(select(Parcel))).all()
        details = (await s.exec(select(ParcelDetail))).all()
    assert len(parcels) == 4
    assert len(details) == 4


async def test_corrupt_file_is_rejected_and_nothing_changes(db_engine, tmp_path):
    await seed(db_engine)
    corrupt = tmp_path / "Cama_Files_20260831.zip"
    with zipfile.ZipFile(FIXTURE) as zin, zipfile.ZipFile(corrupt, "w") as zout:
        for name in zin.namelist():
            data = zin.read(name)
            if name.upper().endswith("PARDAT.DAT"):
                # Letters in every record's numeric taxyr column (bytes 37-41).
                data = b"\n".join(
                    line[:36] + b"ZZZZZ" + line[41:] if len(line) > 41 else line
                    for line in data.split(b"\n")
                )
            zout.writestr(name, data)
    with pytest.raises(TooManyBadRows):
        await ingest_cama(corrupt, engine=db_engine)
    gone = await get(db_engine, Parcel, "Z99 99999 9999")
    assert gone.is_active is True
    assert await get(db_engine, Parcel, "A01 00101 0001") is None
