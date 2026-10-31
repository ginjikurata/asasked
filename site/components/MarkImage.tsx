import { MARK_END, MARK_PATH } from "@/lib/mark";

// The mark as absolutely placed squares, for next/og images (no SVG classes there).
export function MarkImage({ cell, ink, signal }: { cell: number; ink: string; signal: string }) {
  const square = ([x, y]: readonly [number, number], color: string) => (
    <div
      key={`${x}${y}`}
      style={{ position: "absolute", left: x * cell, top: y * cell, width: cell, height: cell, background: color }}
    />
  );
  return (
    <div style={{ position: "relative", display: "flex", width: 6 * cell, height: 4 * cell }}>
      {MARK_PATH.map((p) => square(p, ink))}
      {square(MARK_END, signal)}
    </div>
  );
}
