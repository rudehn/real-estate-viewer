"""CAMA LEGDAT coordinates are Ohio State Plane South (EPSG:3735), US survey feet."""
from functools import lru_cache

from pyproj import Transformer


@lru_cache(maxsize=1)
def _transformer() -> Transformer:
    return Transformer.from_crs("EPSG:3735", "EPSG:4326", always_xy=True)


def state_plane_to_wgs84(x_feet: float | None, y_feet: float | None) -> tuple[float, float] | None:
    if not x_feet or not y_feet:
        return None
    lon, lat = _transformer().transform(x_feet, y_feet)
    return round(lat, 7), round(lon, 7)
