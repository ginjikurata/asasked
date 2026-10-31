import Link from "next/link";
import { SPRITES, pixels } from "@/lib/sprites";

/** 404: a terminal and the guard's red question. Nothing was charged. */
export default function NotFound() {
  const terminal = SPRITES.find((s) => s.name === "terminal")!;
  const ask = SPRITES.find((s) => s.name === "ask")!;
  const tw = terminal.rows[0].length;
  const th = terminal.rows.length;
  return (
    <main>
      <section id="hero" className="column pb-24 pt-24 md:pb-32 md:pt-32">
        <div id="hero-copy">
          <svg viewBox={`0 0 ${tw + 14} ${th}`} className="h-28 w-auto" shapeRendering="crispEdges" aria-hidden>
            {pixels(terminal).map(([x, y, red]) => (
              <rect key={`t${x}-${y}`} x={x} y={y} width="1" height="1" className={red ? "fill-signal" : "fill-ink"} />
            ))}
            {pixels(ask).map(([x, y]) => (
              <rect key={`a${x}-${y}`} x={tw + 3 + x} y={y} width="1" height="1" className="fill-signal" />
            ))}
          </svg>
          <p className="meta mt-8">404 · page not found</p>
          <h1 className="mt-3 text-[40px] font-bold leading-[1.05] tracking-[-0.03em] md:text-[56px]">
            This page is not in the catalog.
          </h1>
          <p className="mt-6 text-[17px] leading-[1.65] text-muted md:text-lg">
            Nothing was charged. The address may be mistyped, or the page has moved.
          </p>
          <div className="receipt mt-8 px-4 pt-3 font-mono text-[12.5px] leading-relaxed">
            <div className="grid grid-cols-[52px_1fr] gap-3">
              <span className="text-faint">cart</span>
              <span>a page that does not exist</span>
              <span className="text-faint">guard</span>
              <span className="font-medium text-signal">ask: did you mean the home page?</span>
            </div>
          </div>
          <Link href="/" className="mt-8 inline-block rounded-full bg-ink px-5 py-2.5 text-[15px] font-medium text-paper hover:opacity-85">
            Go to the home page
          </Link>
        </div>
      </section>
    </main>
  );
}
