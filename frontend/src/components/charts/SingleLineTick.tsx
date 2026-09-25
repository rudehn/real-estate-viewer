const FONT_SIZE = 10;
// Room taken by the tick line and its gap to the label.
const TICK_GUTTER = 10;

let context: CanvasRenderingContext2D | null = null;

function measure(text: string): number {
  if (!context) {
    context = document.createElement("canvas").getContext("2d");
    if (!context) return text.length * FONT_SIZE * 0.6;
    context.font = `${FONT_SIZE}px ${getComputedStyle(document.body).fontFamily}`;
  }
  return context.measureText(text).width;
}

/** Longest prefix of `text` (plus an ellipsis) that fits in `maxWidth` pixels. */
function fit(text: string, maxWidth: number): string {
  if (measure(text) <= maxWidth) return text;
  let lo = 0;
  let hi = text.length;
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2);
    if (measure(text.slice(0, mid).trimEnd() + "…") <= maxWidth) lo = mid;
    else hi = mid - 1;
  }
  return text.slice(0, lo).trimEnd() + "…";
}

/**
 * Category tick for horizontal bar charts: one line, truncated to the axis width.
 *
 * Recharts' default tick wraps long names onto two cramped lines, and
 * truncating by character count either wastes space or overflows because the
 * font is proportional. This measures the label instead. The full name
 * belongs in the tooltip.
 */
export function SingleLineTick(props: {
  x?: number;
  y?: number;
  width?: number;
  payload?: { value: string };
}) {
  const { x = 0, y = 0, width = 120, payload } = props;
  const label = String(payload?.value ?? "");
  return (
    <text x={x} y={y} dy={3.5} textAnchor="end" fontSize={FONT_SIZE} className="fill-muted-foreground">
      <title>{label}</title>
      {fit(label, width - TICK_GUTTER)}
    </text>
  );
}
