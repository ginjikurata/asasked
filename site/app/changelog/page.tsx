import type { Metadata } from "next";
import { PageHead } from "@/components/PageHead";
import { CHANGELOG } from "@/lib/changelog";

export const metadata: Metadata = {
  title: "Changelog",
  description: "What changed in the guard, the dataset, the store and the benchmark, and why.",
  alternates: { canonical: "/changelog" },
};

export default function ChangelogPage() {
  return (
    <main>
      <PageHead kicker="Changelog" title="What changed, and why">
        <p className="text-muted">
          Changes to the guard, the dataset, the sandbox store and the benchmark, newest first. When a result was
          affected, the entry says so.
        </p>
        <p className="text-muted">
          The public repository starts on 31 October 2026. The commit ids below come from the development history
          before it, so they are not in the repository.
        </p>
      </PageHead>
      <div className="column space-y-14">
        {CHANGELOG.map((day) => (
          <section key={day.date} aria-labelledby={`d-${day.date}`}>
            <h2 id={`d-${day.date}`} className="meta text-[13px] text-ink">
              {day.date}
            </h2>
            <ol className="mt-4 space-y-4">
              {day.changes.map((c, i) => (
                <li key={i} className="receipt px-4 pt-3">
                  <div className="flex items-baseline justify-between gap-3 font-mono text-[12px]">
                    <span className="uppercase tracking-wider text-faint">{c.area}</span>
                    {c.commit && <span className="text-faint">{c.commit}</span>}
                  </div>
                  <p className="mt-2 text-[16px] leading-relaxed">{c.text}</p>
                </li>
              ))}
            </ol>
          </section>
        ))}
      </div>
    </main>
  );
}
