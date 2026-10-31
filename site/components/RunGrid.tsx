/**
 * One square per task: filled red — a wrong purchase went through; hollow red — the guard stopped
 * a wrong cart before payment; grey — everything else (right purchase, or nothing bought).
 */
export function RunGrid({ total, wrong, stopped = 0, title }: {
  total: number;
  wrong: number;
  stopped?: number;
  title: string;
}) {
  const cells = Array.from({ length: total }, (_, i) =>
    i < wrong ? "wrong" : i < wrong + stopped ? "stopped" : "other",
  );
  return (
    <figure>
      <div className="grid grid-cols-20 gap-[3px]" role="img" aria-label={`${title}: ${wrong} of ${total} wrong purchases`}>
        {cells.map((c, i) => (
          <span
            key={i}
            className={`aspect-square ${
              c === "wrong" ? "bg-signal" : c === "stopped" ? "border border-signal" : "bg-line"
            }`}
          />
        ))}
      </div>
      <figcaption className="mt-3 flex items-baseline justify-between gap-4">
        <span className="text-sm">{title}</span>
        <span className="font-mono text-sm">
          <span className="text-signal">{wrong}</span>
          <span className="text-faint"> / {total} wrong</span>
        </span>
      </figcaption>
    </figure>
  );
}
