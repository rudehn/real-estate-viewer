// Quantile-bucketed price colors for the map. A linear scale against the max
// price puts every normal sale in the bottom of the ramp the moment one $28M
// outlier is on screen; quantiles give each bucket ~20% of the visible sales.
export const PRICE_COLORS = [
  "#bfdbfe", // blue-200
  "#93c5fd", // blue-300
  "#3b82f6", // blue-500
  "#1d4ed8", // blue-700
  "#172554", // blue-950
];

// On dark tiles the ramp runs the other way: brighter = pricier, and the
// light-theme ramp's darkest bucket would vanish into the basemap.
export const PRICE_COLORS_DARK = [
  "#1e40af", // blue-800
  "#3b82f6", // blue-500
  "#60a5fa", // blue-400
  "#93c5fd", // blue-300
  "#e0f2fe", // sky-100
];

/** Upper bounds of the first N-1 quantile buckets (ascending). */
export function computeQuantileBreaks(
  prices: number[],
  buckets: number = PRICE_COLORS.length
): number[] {
  if (prices.length === 0) return [];
  const sorted = [...prices].sort((a, b) => a - b);
  const breaks: number[] = [];
  for (let i = 1; i < buckets; i++) {
    const idx = Math.min(sorted.length - 1, Math.floor((sorted.length * i) / buckets));
    breaks.push(sorted[idx]);
  }
  return breaks;
}

export function priceToQuantileColor(
  price: number,
  breaks: number[],
  colors: string[] = PRICE_COLORS
): string {
  let bucket = 0;
  while (bucket < breaks.length && price > breaks[bucket]) bucket++;
  return colors[Math.min(bucket, colors.length - 1)];
}

export function getMarkerRadius(acres: number): number {
  return Math.min(20, Math.max(4, Math.sqrt(acres) * 3 + 3));
}
