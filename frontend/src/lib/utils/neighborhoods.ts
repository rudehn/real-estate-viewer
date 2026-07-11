import names from "@/lib/data/neighborhoodNames.json";

const NAMES = names as Record<string, string>;

/** Display name for an appraisal neighborhood code; falls back to the code. */
export function neighborhoodName(code: string | null | undefined): string {
  if (!code) return "—";
  return NAMES[code] ?? code;
}

/** Name truncated for axis labels and table cells. */
export function neighborhoodLabel(code: string | null | undefined, maxLen = 24): string {
  const name = neighborhoodName(code);
  return name.length > maxLen ? name.slice(0, maxLen - 1) + "…" : name;
}
