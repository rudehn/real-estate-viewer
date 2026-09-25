import json
from functools import lru_cache
from pathlib import Path

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, Response
from sqlmodel.ext.asyncio.session import AsyncSession

from api.cache import cache, data_version
from api.errors import ApiError
from db.county_models import Neighborhood, NeighborhoodSummary
from db.engine import get_session
from derived import mapbinary

router = APIRouter(prefix="/map", tags=["map"])
_GEOJSON = Path(__file__).parent.parent.parent / "county" / "data" / "neighborhoods.geojson"
_STATS = ("parcel_count", "residential_count", "parcels_sold_24m", "median_sale_price_24m",
          "median_price_per_sqft_24m", "owner_occupied_share", "median_year_built",
          "median_value_change_pct")


@router.get("/parcels.bin", response_class=FileResponse)
async def parcels_bin(request: Request):
    found = mapbinary.latest_map_binary()
    if not found:
        raise ApiError(503, "map_not_ready", "The parcel map is still being built")
    version, path = found
    etag = f'"v{version}"'
    headers = {"ETag": etag, "Cache-Control": "public, max-age=0, must-revalidate"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return FileResponse(path, media_type="application/octet-stream", headers=headers)


@lru_cache(maxsize=1)
def _boundaries() -> dict:
    return json.loads(_GEOJSON.read_text())


async def _neighborhood_features(session: AsyncSession) -> dict:
    n, ns = Neighborhood.__table__, NeighborhoodSummary.__table__
    rows = (await session.exec(
        sa.select(n, *[ns.c[c] for c in _STATS]).select_from(n)
        .outerjoin(ns, ns.c.code == n.c.code)
    )).mappings().all()
    by_code = {r["code"]: dict(r) for r in rows}
    features = []
    for feature in _boundaries()["features"]:
        code = feature["properties"].get("code")
        props = {"code": code, **(by_code.get(code) or {"name": feature["properties"].get("name")})}
        features.append({"type": "Feature", "geometry": feature["geometry"], "properties": props})
    return {"type": "FeatureCollection", "features": features}


@router.get("/neighborhoods")
async def neighborhoods(session: AsyncSession = Depends(get_session)) -> dict:
    version = await data_version(session)
    return await cache.get_or_compute(
        ("neighborhood-geojson",), version, lambda: _neighborhood_features(session)
    )
