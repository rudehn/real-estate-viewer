"""Regenerate the neighborhood boundary/name assets from the county GIS.

The Montgomery County auditor publishes appraisal neighborhoods (the same
NBHD codes used in the sales files) as the "Neighborhood 2020" layer:

  https://gis.mcohio.org/server/rest/services/VantagePoints/AUDGIS_Advance/MapServer/19

This script writes two committed frontend assets so the app has no runtime
dependency on the county GIS server:

  frontend/public/neighborhoods.geojson       - simplified polygons for the choropleth
  frontend/src/lib/data/neighborhoodNames.json - code -> display name lookup

Run with: uv run python scripts/fetch_neighborhoods.py
"""
import json
import urllib.parse
import urllib.request
from pathlib import Path

LAYER_URL = (
    "https://gis.mcohio.org/server/rest/services/VantagePoints/"
    "AUDGIS_Advance/MapServer/19/query"
)
REPO = Path(__file__).parent.parent
GEOJSON_OUT = REPO / "frontend" / "public" / "neighborhoods.geojson"
NAMES_OUT = REPO / "frontend" / "src" / "lib" / "data" / "neighborhoodNames.json"

# ~30m simplification and 5-decimal coordinates: plenty for a county-wide
# choropleth, and keeps the asset small enough to ship.
SIMPLIFY_OFFSET = 0.0003
COORD_DECIMALS = 5


def round_coords(obj):
    if isinstance(obj, float):
        return round(obj, COORD_DECIMALS)
    if isinstance(obj, list):
        return [round_coords(x) for x in obj]
    return obj


def main() -> None:
    params = urllib.parse.urlencode({
        "where": "1=1",
        "outFields": "NBHD_1,NBHD_NAME",
        "returnGeometry": "true",
        "outSR": "4326",
        "maxAllowableOffset": str(SIMPLIFY_OFFSET),
        "f": "geojson",
    })
    # The county server rejects urllib's default User-Agent.
    req = urllib.request.Request(
        f"{LAYER_URL}?{params}", headers={"User-Agent": "real-estate-viewer/1.0"}
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.load(resp)
    if "features" not in data:
        raise RuntimeError(f"Unexpected response from county GIS: {str(data)[:300]}")

    names: dict[str, str] = {}
    features = []
    for f in data["features"]:
        code = f["properties"].get("NBHD_1")
        name = (f["properties"].get("NBHD_NAME") or "").strip()
        if not code:
            continue
        if name:
            names[code] = name
        features.append({
            "type": "Feature",
            "properties": {"code": code, "name": name or code},
            "geometry": {
                "type": f["geometry"]["type"],
                "coordinates": round_coords(f["geometry"]["coordinates"]),
            },
        })

    GEOJSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    NAMES_OUT.parent.mkdir(parents=True, exist_ok=True)
    GEOJSON_OUT.write_text(json.dumps(
        {"type": "FeatureCollection", "features": features},
        separators=(",", ":"),
    ))
    NAMES_OUT.write_text(json.dumps(dict(sorted(names.items())), indent=1))
    print(f"{len(features)} features -> {GEOJSON_OUT} "
          f"({GEOJSON_OUT.stat().st_size / 1e6:.2f} MB)")
    print(f"{len(names)} names -> {NAMES_OUT}")


if __name__ == "__main__":
    main()
