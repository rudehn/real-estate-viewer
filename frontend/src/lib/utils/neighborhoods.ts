import names from "@/lib/data/neighborhoodNames.json";

const NAMES = names as Record<string, string>;

// Dayton names its neighborhoods after the planning district first, e.g.
// "SE PRIORITY BOARD-SOUTH PARK", so the distinguishing part comes last.
const PRIORITY_BOARD = /^(.+?)\s+PRIORITY BOARD\s*-\s*(.+)$/;

/** Display name for an appraisal neighborhood code; falls back to the code. */
export function neighborhoodName(code: string | null | undefined): string {
  if (!code) return "—";
  return NAMES[code] ?? code;
}

/** Compact name that leads with the distinguishing part: "SOUTH PARK (SE)". */
export function neighborhoodShortName(code: string | null | undefined): string {
  const name = neighborhoodName(code);
  const board = name.match(PRIORITY_BOARD);
  return board ? `${board[2]} (${board[1]})` : name;
}

/** Short name truncated for legends, selects and table cells. */
export function neighborhoodLabel(code: string | null | undefined, maxLen = 24): string {
  const name = neighborhoodShortName(code);
  return name.length > maxLen ? name.slice(0, maxLen - 1) + "…" : name;
}
