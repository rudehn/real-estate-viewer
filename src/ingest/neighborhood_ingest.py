"""Official neighborhood names from the county's monthly codes page."""
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine

from county.neighborhood_codes import neighborhood_display_name, parse_neighborhood_codes
from db.county_models import Neighborhood
from ingest.bulk import upsert


async def ingest_neighborhood_names(html_path: Path, engine: AsyncEngine | None = None) -> int:
    if engine is None:
        from db.engine import engine as default_engine

        engine = default_engine
    names = parse_neighborhood_codes(Path(html_path).read_bytes())
    rows = [
        {"code": code, "name": name, "display_name": neighborhood_display_name(name)}
        for code, name in names.items()
    ]
    table = Neighborhood.__table__
    async with engine.begin() as conn:
        for i in range(0, len(rows), 1000):
            stmt = upsert(conn)(table).values(rows[i : i + 1000])
            await conn.execute(stmt.on_conflict_do_update(
                index_elements=["code"],
                set_={"name": stmt.excluded.name, "display_name": stmt.excluded.display_name},
            ))
    return len(rows)
