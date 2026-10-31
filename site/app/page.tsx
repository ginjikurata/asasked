import type { Metadata } from "next";
import { GitHubLink } from "@/components/Chrome";
import { GuardDemo } from "@/components/GuardDemo";
import { LiveTry } from "@/components/LiveTry";
import { HeroSlip } from "@/components/HeroSlip";
import { LoadingGate } from "@/components/LoadingGate";
import { ReprintButton } from "@/components/PixelField";
import { RunGrid } from "@/components/RunGrid";
import { GUARD_STEPS, LIMITATIONS, RESULTS, STORE, UNSAID, VI_CONSTRAINTS, VI_URL } from "@/lib/content";

export const metadata: Metadata = { alternates: { canonical: "/" } };

function Section({ id, n, title, children }: { id: string; n: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="column pt-24 md:pt-32">
      <p className="meta">{n}</p>
      <h2 className="mt-2 text-[34px] font-semibold leading-tight tracking-tight md:text-[40px]">{title}</h2>
      <div className="mt-6 space-y-5 text-[17px] leading-[1.65] md:text-lg">{children}</div>
    </section>
  );
}

// ASCII only: box-drawing glyphs and arrows fall back to other fonts and break the alignment.
const FLOW = String.raw`
 words --+    +-------------+         +-------------+    +--> proceed
         +--> | two models  | facts   | plain code  | ---+
 cart ---+    | extract     | ------> | decides     |    +--> ask + question
              +-------------+         +-------------+
               disagreement            same inputs,
               only warns              same answer`;

export default function Home() {
  const n = RESULTS.naive;
  return (
    <>
      <LoadingGate />
      <main id="top">
        {/* ── Hero ── */}
        {/* room above and below the intro: the field grows into those bands, across the column */}
        <section id="hero" className="column pb-28 pt-28 md:pb-40 md:pt-40">
          <div id="hero-copy">
          <p className="text-muted">Pre-checkout guard for AI shopping agents</p>
          <h1 className="mt-4 text-[44px] font-bold leading-[1.02] tracking-[-0.03em] md:text-[64px]">
            The agent stayed within its mandate. Did it buy what you asked&nbsp;for?
          </h1>
          <p className="mt-7 text-[17px] leading-[1.65] md:text-lg">
            Verifiable Intent proves an agent kept to its formal limits: approved items, an amount in range, an allowed
            merchant. It does not check the cart against what the person said. AsAsked does, between “the cart is ready”
            and “pay”, and answers <span className="font-mono">proceed</span> or{" "}
            <span className="font-mono text-signal">ask</span>, with a ready question for the person.
          </p>
          <HeroSlip />
          <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-3">
            <a href="#try" className="rounded-full bg-ink px-5 py-2.5 text-[15px] font-medium text-paper hover:opacity-85">
              Try the guard
            </a>
            <a href="#spec" className="text-[15px] font-medium hover:underline">
              Spec →
            </a>
          </div>
          <div className="mt-10 flex items-start justify-between gap-6">
            <p className="meta">
              {STORE.products} products · {STORE.tasks} labelled tasks · {STORE.templates} trap templates · baseline
              agent: {n.wrongWithout} wrong purchases without the guard, {n.wrongWith} with it
            </p>
            <ReprintButton />
          </div>
          {/* only where there is a cursor to play with */}
          <p className="meta mt-3 hidden [@media(pointer:fine)]:block">
            <span className="text-signal">●</span> Move the cursor onto a line in the margins: a payment passing it
            stops and gets asked about. Here, you are the guard.
          </p>
          </div>
        </section>

        {/* ── 01 Try ── */}
        <Section id="try" n="01" title="Try it">
          <p>
            Eight tasks from the open half of the dataset. A baseline agent bought the first search result; payment
            would have gone through. Pick a request and see what the guard says, then switch to the right purchase.
          </p>
          <div className="pt-2">
            <GuardDemo />
          </div>
          <h3 className="pt-8 font-medium text-ink">Or write your own</h3>
          <p>
            Type a request the way you&apos;d say it to a person. A real agent shops in the sandbox tennis store, and the
            guard checks the cart against your words before it pays.
          </p>
          <div className="pt-2">
            <LiveTry />
          </div>
        </Section>

        {/* ── 02 Gap ── */}
        <Section id="gap" n="02" title="The gap">
          <p>
            <a href={VI_URL} className="link">
              Verifiable Intent
            </a>{" "}
            (draft v0.1, Mastercard and Google) cryptographically binds a purchase to a delegation chain. Everything it
            checks is real, and it verifies. The person&apos;s own words travel in one field,{" "}
            <code className="font-mono text-[0.92em]">prompt_summary</code>: optional, marked “for audit trail”, read by
            no verification code.
          </p>
          <div className="overflow-hidden rounded-lg border border-line bg-paper">
            <table className="w-full text-left font-mono text-[13px]">
              <thead className="border-b border-line text-faint">
                <tr>
                  <th className="px-4 py-2.5 font-normal">constraint type</th>
                  <th className="px-4 py-2.5 font-normal">expresses</th>
                </tr>
              </thead>
              <tbody>
                {VI_CONSTRAINTS.map((c) => (
                  <tr key={c.name} className="border-t border-line first:border-t-0">
                    <td className="px-4 py-2.5">{c.name}</td>
                    <td className="px-4 py-2.5 text-muted">{c.expresses}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p>
            None of them can say{" "}
            {UNSAID.map((u, i) => (
              <span key={u}>
                <span className="font-mono text-[0.92em]">“{u}”</span>
                {i < UNSAID.length - 2 ? ", " : i === UNSAID.length - 2 ? " or " : ""}
              </span>
            ))}
            . In eight constructed scenarios, each with a genuine signed chain, six purchases pass Verifiable Intent
            completely while contradicting the request. The scenarios were written to show the gap exists; they are not
            a failure rate.
          </p>
        </Section>

        {/* ── 03 Method ── */}
        <Section id="guard" n="03" title="Method">
          <pre className="overflow-x-auto rounded-lg border border-line bg-paper p-4 font-mono text-[11.5px] leading-snug text-muted md:text-[12.5px]">
            {FLOW.slice(1)}
          </pre>
          {GUARD_STEPS.map((s) => (
            <p key={s.n}>
              <span className="font-semibold">{s.title}.</span> {s.body}
            </p>
          ))}
          <p>
            The split is the point. “The AI decided so” is worth nothing in a dispute. “The person asked to be able to
            return it; the item is final sale” is worth something, because anyone can check it by hand.
          </p>
        </Section>

        {/* ── 04 Benchmark ── */}
        <Section id="benchmark" n="04" title="Benchmark">
          <p>
            Agents shop in an open sandbox store: {STORE.products} products from {STORE.merchants} merchants. Traps come
            from the catalog&apos;s structure, as in a real store: the same shoe in another colour at the same price to
            the cent, the same item cheaper at a shop with no returns or with two-week delivery. Every order goes through
            a real Verifiable Intent chain. {STORE.tasks} labelled tasks, {STORE.hidden} of them hidden; agents are scored
            against the human label, never against the guard.
          </p>
          <p className="meta">baseline agent: buys the first search result · one square per task, all {n.tasks}</p>
          <div className="receipt grid gap-8 p-5 pb-8 md:grid-cols-2">
            <RunGrid total={n.tasks} wrong={n.wrongWithout} title="No guard" />
            <RunGrid total={n.tasks} wrong={n.wrongWith} stopped={n.caught} title="With the guard" />
          </div>
          <p className="meta">
            ■ wrong purchase paid · □ wrong cart stopped before payment ({n.caught}) · right purchases stopped for
            nothing: {n.falseStops}. Every wrong purchase passed Verifiable Intent.
          </p>
          {RESULTS.preliminary && (
            <p className="rounded-lg border border-dashed border-line bg-paper p-4 text-[15px] text-muted">
              Preliminary, run of {RESULTS.runDate}. Real models (Claude, GPT, DeepSeek, MiniMax, Nemotron) are being
              re-run after three fixes to the test bench; their results will appear here, including how often the guard
              stops them for nothing.
            </p>
          )}
        </Section>

        {/* ── 05 Spec ── */}
        <Section id="spec" n="05" title="Spec and code">
          <p>
            AsAsked is an open reference, not a product. The guard&apos;s behaviour is written down as a spec, so that a
            second implementation can be built and checked against it. The library, the sandbox store and the open half
            of the dataset are open source.
          </p>
          <pre className="overflow-x-auto rounded-lg border border-line bg-paper p-4 font-mono text-[12.5px] leading-relaxed">
{`from asasked.guard import Guard

guard = Guard(request="Black ASICS in size 42, "
                      "I need to be able to return them.",
              today="Monday, 2 November 2026")
guard.check(cart, mandate, find)
# {"decision": "ask", "reasons": [...], "question": "..."}`}
          </pre>
          <ul className="space-y-1.5 font-mono text-[14px]">
            <li>
              <GitHubLink path="/blob/main/spec/guard.md">spec/guard.md</GitHubLink>{" "}
              <span className="text-faint">— what a guard must do</span>
            </li>
            <li>
              <GitHubLink path="/tree/main/src/asasked">src/asasked</GitHubLink>{" "}
              <span className="text-faint">— guard, store, harness</span>
            </li>
            <li>
              <GitHubLink path="/tree/main/data">data/</GitHubLink>{" "}
              <span className="text-faint">— the open half of the dataset</span>
            </li>
          </ul>
        </Section>

        {/* ── 06 Limits ── */}
        <Section id="limits" n="06" title="Limitations">
          <ul className="space-y-4">
            {LIMITATIONS.map((l) => (
              <li key={l} className="border-l-2 border-line pl-4 text-muted">
                {l}
              </li>
            ))}
          </ul>
        </Section>
      </main>
    </>
  );
}
