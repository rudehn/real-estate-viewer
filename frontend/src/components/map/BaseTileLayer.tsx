"use client";

import { TileLayer } from "react-leaflet";
import { usePublicConfig } from "@/components/providers/PublicConfigProvider";

const OSM_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const OSM_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';

const CARTO_DARK_URL = "https://basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}{r}.png";
const CARTO_ATTRIBUTION = `${OSM_ATTRIBUTION} &copy; <a href="https://carto.com/attributions">CARTO</a>`;

// The basemap under every map. Dark mode prefers CARTO's dark style, which
// needs a key (free, no account: carto.com/basemaps/apikey); without one CARTO
// serves an "API KEY REQUIRED" watermark on every tile. With no key configured,
// dark mode inverts the OSM tiles instead (see .map-tiles-dark in globals.css).
export default function BaseTileLayer({ isDark }: { isDark: boolean }) {
  const { cartoApiKey } = usePublicConfig();

  if (isDark && cartoApiKey) {
    return (
      <TileLayer
        key="carto-dark"
        attribution={CARTO_ATTRIBUTION}
        url={`${CARTO_DARK_URL}?key=${encodeURIComponent(cartoApiKey)}`}
      />
    );
  }

  return (
    <TileLayer
      // Leaflet reads className only when the layer is created.
      key={isDark ? "osm-dark" : "osm"}
      attribution={OSM_ATTRIBUTION}
      url={OSM_URL}
      className={isDark ? "map-tiles-dark" : undefined}
    />
  );
}
