import { SPRITES, pixels, type Sprite } from "@/lib/sprites";

function Pixels({ sprite, className }: { sprite: Sprite; className?: string }) {
  const w = sprite.rows[0].length;
  const h = sprite.rows.length;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className={className} shapeRendering="crispEdges" aria-hidden>
      {pixels(sprite).map(([x, y, red]) => (
        <rect key={`${x}-${y}`} x={x} y={y} width="1" height="1" className={red ? "fill-signal" : "fill-ink"} />
      ))}
    </svg>
  );
}

/**
 * The entry screen: a card slides into a payment terminal, then the page shows.
 * Pure CSS, so it lifts on its own even without JavaScript; skipped with reduced motion.
 */
export function LoadingGate() {
  const card = SPRITES.find((s) => s.name === "card")!;
  const terminal = SPRITES.find((s) => s.name === "terminal")!;
  return (
    <div className="gate" aria-hidden>
      <div className="flex flex-col items-center">
        {/* the card is drawn first, so the terminal covers it as it goes in */}
        <div className="relative h-[120px] w-[96px]">
          <Pixels sprite={card} className="gate-card absolute left-1/2 top-0 h-auto w-[96px] -translate-x-1/2" />
          <div className="absolute bottom-0 left-1/2 -translate-x-1/2 bg-paper">
            <Pixels sprite={terminal} className="h-auto w-[56px]" />
          </div>
        </div>
        <p className="mt-5 text-[17px] font-semibold tracking-tight">AsAsked</p>
        <p className="meta mt-1">checking the cart</p>
      </div>
    </div>
  );
}
