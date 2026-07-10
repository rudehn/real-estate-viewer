// Interpolates between two hex colors based on a 0–1 value
function lerpHex(colorA: string, colorB: string, t: number): string {
  const hex = (s: string) => [
    parseInt(s.slice(1, 3), 16),
    parseInt(s.slice(3, 5), 16),
    parseInt(s.slice(5, 7), 16),
  ];
  const [r1, g1, b1] = hex(colorA);
  const [r2, g2, b2] = hex(colorB);
  const rv = Math.round(r1 + (r2 - r1) * t);
  const gv = Math.round(g1 + (g2 - g1) * t);
  const bv = Math.round(b1 + (b2 - b1) * t);
  return `#${[rv, gv, bv].map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}

const LOW_COLOR = "#bfdbfe"; // blue-200
const HIGH_COLOR = "#1d4ed8"; // blue-700

export function priceToColor(
  price: number,
  min: number,
  max: number
): string {
  if (max <= min) return LOW_COLOR;
  const t = Math.max(0, Math.min(1, (price - min) / (max - min)));
  return lerpHex(LOW_COLOR, HIGH_COLOR, t);
}

export function getMarkerRadius(acres: number): number {
  return Math.min(20, Math.max(4, Math.sqrt(acres) * 3 + 3));
}
