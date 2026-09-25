import json
from pathlib import Path

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from db.county_models import Dwelling, ParcelFeature
from ingest.cama_ingest import ingest_cama, sketch_lines

FIXTURE = Path(__file__).parent.parent / "fixtures" / "county" / "cama_fixture.zip"


async def dwelling(db_engine, parcel_id, card=1):
    async with AsyncSession(db_engine) as s:
        return await s.get(Dwelling, (parcel_id, card))


async def test_dwelling_decoded(db_engine):
    counts = await ingest_cama(FIXTURE, engine=db_engine)
    assert counts["dwelling"] == 5
    d = await dwelling(db_engine, "A01 00101 0001")
    assert (d.living_sqft, d.first_floor_sqft, d.beds, d.full_baths, d.half_baths) == (
        2464, 900, 3, 1, 0
    )
    assert (d.style_code, d.style, d.stories) == ("05", "OLD STYLE", 2.0)
    assert (d.year_built, d.year_built_is_placeholder) == (1919, True)
    assert (d.grade, d.grade_label, d.condition) == ("C+", "AVERAGE +", "VERY GOOD")
    assert (d.exterior, d.basement, d.heating, d.fuel) == ("FRAME", "PART", "CENTRAL HEAT", "OIL")
    assert d.has_central_air is False
    assert (d.attached_garage_sqft, d.basement_garage_cars) == (0, 1)


async def test_attached_garage_and_air(db_engine):
    await ingest_cama(FIXTURE, engine=db_engine)
    ranch = await dwelling(db_engine, "N64 00101 0003")
    assert (ranch.attached_garage_sqft, ranch.has_central_air, ranch.style) == (384, True, "RANCH")
    second = await dwelling(db_engine, "A01 00102 0069", card=2)
    assert (second.living_sqft, second.attached_garage_sqft) == (720, 552)


async def test_sketch_json(db_engine):
    await ingest_cama(FIXTURE, engine=db_engine)
    ranch = await dwelling(db_engine, "N64 00101 0003")
    lines = json.loads(ranch.sketch)
    assert [line["line"] for line in lines] == [0, 1, 2]
    assert lines[0] == {"line": 0, "codes": [], "area": 1008, "vector": "A0CU24R42D24L42"}
    assert lines[1]["codes"] == ["13"]
    assert lines[2]["codes"] == ["33", "32"]


def test_sketch_lines_sorts_and_drops_blank_codes():
    rows = [
        {"lline": 1, "lower": None, "first": "13", "second": None, "third": None,
         "area": 384, "vect": "A1R42"},
        {"lline": 0, "lower": None, "first": None, "second": None, "third": None,
         "area": 1008, "vect": "A0CU24"},
    ]
    assert [line["line"] for line in sketch_lines(rows)] == [0, 1]
    assert sketch_lines(rows)[0]["codes"] == []


async def test_features(db_engine):
    counts = await ingest_cama(FIXTURE, engine=db_engine)
    assert counts["parcel_feature"] == 6
    async with AsyncSession(db_engine) as s:
        items = (await s.exec(
            select(ParcelFeature).where(ParcelFeature.parcel_id == "R72 00304 0025")
        )).all()
    garage = next(i for i in items if i.code == "RG1")
    assert garage.description == "FRAME OR CB DETACHED GARAGE"
    assert (garage.area_sqft, garage.width_ft, garage.length_ft, garage.year_built) == (
        960, 40, 24, 2000
    )
    assert garage.condition == "AVERAGE"
