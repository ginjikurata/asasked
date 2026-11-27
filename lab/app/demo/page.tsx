import type { Metadata } from "next";
import { REQUEST, RUNS, type Step, type Verdict } from "@/lib/demoRuns";

export const metadata: Metadata = {
  title: "Demo: an agent shops, the guard checks",
  description:
    "A naive AI agent buys a tennis racket at five test shops. Four try to change the payment; the AsAsked guard checks each one before anything is signed.",
};

const VERDICT: Record<Verdict, { label: string; cls: string }> = {
  proceed: { label: "Allowed", cls: "border-pass/30 bg-pass/10 text-pass" },
  ask: { label: "Asks you", cls: "border-[#c98a12]/30 bg-[#c98a12]/10 text-[#9a6a0c]" },
  refuse: { label: "Refused", cls: "border-signal/30 bg-signal-soft text-signal-ink" },
};

function Pill({ v }: { v: Verdict }) {
  return (
    <span className={`inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 font-mono text-[11px] uppercase tracking-wider ${VERDICT[v].cls}`}>
      {VERDICT[v].label}
    </span>
  );
}

const WHO: Record<Step["who"], string> = { agent: "Agent", shop: "Shop", pay: "Agent pays", guard: "Guard", you: "You" };

function Row({ s }: { s: Step }) {
  if (s.who === "guard") {
    return (
      <li className="rounded-2xl border border-line bg-paper p-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-[11px] uppercase tracking-wider text-faint">Guard</span>
          <Pill v={s.verdict} />
        </div>
        <p className="mt-2 text-[15px]">{s.text}</p>
        <p className="mt-2 break-words font-mono text-[12px] leading-relaxed text-muted">Seller check: {s.seller}</p>
      </li>
    );
  }
  const tone =
    s.who === "shop" && s.note
      ? "border-l-2 border-[#c98a12] pl-3 italic text-ink"
      : s.who === "pay"
        ? "font-mono text-[13px] text-ink"
        : s.who === "you"
          ? "font-medium text-ink"
          : "text-muted";
  return (
    <li className="grid grid-cols-[76px_1fr] gap-3 sm:grid-cols-[96px_1fr]">
      <span className="pt-0.5 font-mono text-[11px] uppercase tracking-wider text-faint">
        {s.who === "shop" && s.note ? "Shop note" : WHO[s.who]}
      </span>
      <p className={`min-w-0 break-words text-[15px] ${tone}`}>{s.text}</p>
    </li>
  );
}

export default function Demo() {
  return (
    <main className="column pt-10 sm:pt-14">
      <p className="inline-flex items-center gap-2 rounded-full border border-signal/30 bg-signal-soft px-2.5 py-1 font-mono text-[11px] uppercase tracking-wider text-signal-ink">
        Demo · test coins only
      </p>
      <h1 className="mt-4 text-[32px] font-semibold leading-[1.08] tracking-[-0.02em] sm:text-[44px]">
        An agent goes shopping. The guard checks every payment.
      </h1>
      <p className="mt-3 max-w-[60ch] text-[17px] text-muted">
        We gave a deliberately naive agent one request and sent it to five test shops. It believes whatever a shop
        tells it. Four of the shops use that to try to change the payment. Here is what the AsAsked guard did each
        time, before anything reached your wallet.
      </p>

      <section className="mt-10 rounded-3xl bg-panel p-5 sm:p-8">
        <p className="font-mono text-[11px] uppercase tracking-wider text-faint">You asked for</p>
        <p className="mt-1 text-[22px] font-semibold tracking-[-0.01em]">“{REQUEST.text}”</p>
        <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-[15px] text-muted">
          <div>
            <dt className="inline">Up to </dt>
            <dd className="inline font-medium text-ink">{REQUEST.limit}</dd>
          </div>
          <div>
            <dt className="inline">Pay in </dt>
            <dd className="inline font-medium text-ink">{REQUEST.token}</dd>
          </div>
          <div>
            <dt className="inline">Network </dt>
            <dd className="inline font-medium text-ink">{REQUEST.network}</dd>
          </div>
        </dl>
        <p className="mt-4 max-w-[60ch] text-[15px] text-muted">
          The guard can say one of three things: <Pill v="proceed" /> the payment matches what you asked,{" "}
          <Pill v="ask" /> something differs and only you can decide, or <Pill v="refuse" /> the payment is wrong and no
          answer can approve it. Even when it allows a payment, nothing is paid until you sign.
        </p>
      </section>

      <nav aria-label="Shops" className="mt-10">
        <ul className="flex flex-col gap-2">
          {RUNS.map((r, i) => (
            <li key={r.id}>
              <a href={`#${r.id}`} className="flex items-center gap-3 rounded-2xl border border-line bg-panel px-4 py-3 hover:border-ink">
                <span className="font-mono text-[12px] text-signal-ink">0{i + 1}</span>
                <span className="min-w-0 flex-1">
                  <span className="font-medium">{r.shop}</span>
                  <span className="block truncate text-[13px] text-muted">{r.trick}</span>
                </span>
                <Pill v={r.outcome.verdict} />
              </a>
            </li>
          ))}
        </ul>
      </nav>

      {RUNS.map((r, i) => (
        <section key={r.id} id={r.id} className="mt-14 scroll-mt-20">
          <p className="font-mono text-[11px] uppercase tracking-wider text-faint">
            Shop 0{i + 1} · {r.domain}
          </p>
          <h2 className="mt-1 text-[22px] font-semibold tracking-[-0.01em]">{r.shop}</h2>
          <p className="mt-1 max-w-[60ch] text-[15px] text-muted">{r.trick}</p>
          <ol className="mt-5 flex flex-col gap-3 rounded-3xl bg-panel p-4 sm:p-6">
            {r.steps.map((s, j) => (
              <Row key={j} s={s} />
            ))}
          </ol>
          <p className="mt-3 flex flex-wrap items-center gap-2 text-[15px]">
            <span className="text-muted">Result:</span>
            <span className="font-medium">{r.outcome.text}</span>
          </p>
        </section>
      ))}

      <section className="mt-16 rounded-3xl bg-panel p-5 sm:p-8">
        <h2 className="text-[22px] font-semibold tracking-[-0.01em]">What this is, and isn&apos;t</h2>
        <ul className="mt-4 flex flex-col gap-3">
          {[
            "These are recorded runs of the real guard from our agent-wallet prototype. The guard's decisions and reasons are shown as it gave them; addresses are shortened.",
            "The shops are test shops we built, on Solana devnet with test coins. No real money moved and no real store was involved.",
            "The agent is scripted to be naive on purpose: it follows the shops' notes. A real AI agent can be fooled the same way, which is why the check sits outside the agent.",
            "The seller check compares the address with a list the shop signed with its own key. That is what catches the hacked checkout, where the invoice itself was wrong.",
          ].map((t) => (
            <li key={t} className="flex gap-3 text-[15px]">
              <span className="mt-[7px] size-2 shrink-0 bg-signal" aria-hidden />
              {t}
            </li>
          ))}
        </ul>
      </section>

      <p className="mt-10 text-sm text-muted">
        Agent checkout for real stores is on the{" "}
        <a href="/coming" className="link text-ink">
          roadmap
        </a>
        . Until then, the{" "}
        <a href="/stores" className="link text-ink">
          checked store list
        </a>{" "}
        is live. Questions:{" "}
        <a href="https://x.com/asaskedconcord" className="link text-ink">
          @asaskedconcord
        </a>{" "}
        on X.
      </p>
    </main>
  );
}
