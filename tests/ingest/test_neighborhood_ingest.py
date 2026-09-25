from pathlib import Path

from sqlmodel.ext.asyncio.session import AsyncSession

from db.county_models import Neighborhood
from ingest.cama_ingest import ingest_cama
from ingest.neighborhood_ingest import ingest_neighborhood_names

FIXTURE = Path(__file__).parent.parent / "fixtures" / "county" / "cama_fixture.zip"
PAGE = (
    b"<tr>\r\n<td>\r\n48150000\r\n</td>\r\n<td>\r\nNORTH BUTLER TOWNSHIP\r\n</td>\r\n</tr>\r\n"
    b"<tr>\r\n<td>\r\n82000ARL\r\n</td>\r\n<td>\r\nSW PRIORITY BOARD-ARLINGTON HEIGHTS\r\n"
    b"</td>\r\n</tr>"
)


async def test_official_names_win_over_cama_names_in_either_order(db_engine, tmp_path):
    page = tmp_path / "neighborhood_codes_20260901.htm"
    page.write_bytes(PAGE)
    assert await ingest_neighborhood_names(page, engine=db_engine) == 2
    await ingest_cama(FIXTURE, engine=db_engine)
    async with AsyncSession(db_engine) as s:
        butler = await s.get(Neighborhood, "48150000")
        arlington = await s.get(Neighborhood, "82000ARL")
    assert butler.name == "NORTH BUTLER TOWNSHIP"
    assert butler.tax_district == "A01"
    assert (arlington.name, arlington.display_name) == (
        "SW PRIORITY BOARD-ARLINGTON HEIGHTS", "ARLINGTON HEIGHTS"
    )
