"use client";

import { useEffect, useMemo, useState } from "react";
import examples from "@/lib/examples.json";

type Item = { name: string; qty: number; price: string; merchant: string; returns: string; delivery_days: number };
type Outcome = { cart: Item[]; vi: string; decision: string; reasons: string[]; question: string | null };
type Example = { id: string; template: string; request: string; trap: string; wrong: Outcome; right: Outcome | null };

const EXAMPLES = examples as Example[];

/** Short chip labels for the templates shown in the demo. */
const LABEL: Record<string, string> = {
  "refund-variant": "returns",
  deadline: "deadline",
  "cheapest-returnable": "cheapest, returnable",
  "soft-colour": "colour, hedged",
  cans: "three cans",
  exclusion: "anything but Yonex",
  "two-sizes": "two sizes",
  "over-budget": "over budget",
};

type Line = { k: string; v: string; tone?: "pass" | "signal" | "muted" };

function lines(ex: Example, which: "wrong" | "right"): Line[] {
  const o = which === "wrong" ? ex.wrong : ex.right;
  if (!o) return [];
  const out: Line[] = [{ k: "$ request", v: `“${ex.request}”` }];
  o.cart.forEach((it, i) =>
    out.push({
      k: i === 0 ? "cart" : "",
      v: `${it.qty} × ${it.name} · ${it.merchant} · ${it.price} · ${it.returns} · ${it.delivery_days}d delivery`,
    }),
  );
  out.push({ k: "VI", v: "✓ chain valid · constraints satisfied", tone: "pass" });
  out.push({ k: "guard", v: o.decision, tone: o.decision === "ask" ? "signal" : "pass" });
  o.reasons.forEach((r) => out.push({ k: "", v: `- ${r}`, tone: "muted" }));
  if (o.question) out.push({ k: "→ person", v: o.question.split("\n").at(-1) ?? "", tone: "muted" });
  return out;
}

export function GuardDemo() {
  const [index, setIndex] = useState(0);
  const [which, setWhich] = useState<"wrong" | "right">("wrong");
  const [shown, setShown] = useState(0);
  const ex = EXAMPLES[index];
  const all = useMemo(() => lines(ex, which), [ex, which]);
  const outcome = which === "wrong" ? ex.wrong : ex.right;

  // lines appear one by one, like a run; instantly with reduced motion
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setShown(all.length);
      return;
    }
    setShown(0);
    let n = 0;
    const t = window.setInterval(() => {
      n += 1;
      setShown(n);
      if (n >= all.length) window.clearInterval(t);
    }, 160);
    return () => window.clearInterval(t);
  }, [all]);

  return (
    <div>
      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Requests">
        {EXAMPLES.map((e, i) => (
          <button
            key={e.id}
            type="button"
            role="tab"
            aria-selected={i === index}
            onClick={() => {
              setIndex(i);
              setWhich("wrong");
            }}
            className={`rounded-full border px-3 py-1 font-mono text-[12px] transition-colors ${
              i === index ? "border-ink bg-ink text-paper" : "border-line text-muted hover:border-ink hover:text-ink"
            }`}
          >
            {LABEL[e.template] ?? e.template}
          </button>
        ))}
      </div>

      <div className="receipt relative mt-5">
        <div className="flex items-center justify-between gap-3 border-b border-dashed border-faint/50 px-4 py-2">
          <span className="meta hidden sm:inline">asasked · guard.check(cart)</span>
          <div className="ml-auto flex gap-1 font-mono text-[12px]" role="radiogroup" aria-label="Cart">
            {(["wrong", "right"] as const).map((w) => (
              <button
                key={w}
                type="button"
                role="radio"
                aria-checked={which === w}
                disabled={w === "right" && !ex.right}
                onClick={() => setWhich(w)}
                className={`rounded px-2 py-0.5 disabled:opacity-40 ${
                  which === w ? "bg-paper text-ink" : "text-faint hover:text-ink"
                }`}
              >
                {w === "wrong" ? "first search result" : ex.right ? "right purchase" : "right: buy nothing"}
              </button>
            ))}
          </div>
        </div>
        <dl className="min-h-[260px] space-y-1.5 p-4 font-mono text-[12.5px] leading-relaxed md:text-[13px]">
          {all.slice(0, shown).map((l, i) => (
            <div key={i} className="grid grid-cols-[72px_1fr] gap-3 md:grid-cols-[84px_1fr]">
              <dt className="text-faint">{l.k}</dt>
              <dd
                className={
                  l.tone === "pass"
                    ? "text-pass"
                    : l.tone === "signal"
                      ? "font-medium text-signal"
                      : l.tone === "muted"
                        ? "text-muted"
                        : ""
                }
              >
                {l.v}
              </dd>
            </div>
          ))}
          {shown < all.length && <span className="inline-block h-4 w-2 animate-pulse bg-ink align-middle" />}
        </dl>
        {/* the verdict, stamped on the slip once it has printed */}
        {shown >= all.length && outcome && (
          <span
            key={`${ex.id}-${which}`}
            className={`stamp absolute bottom-8 right-5 ${outcome.decision === "ask" ? "text-signal" : "text-pass"}`}
          >
            {outcome.decision}
          </span>
        )}
      </div>
      <p className="meta mt-3">
        Trap in this task: {ex.trap}. Carts and answers are real output of the sandbox and the guard&apos;s deterministic
        check (task {ex.id}); here the facts come from the task&apos;s label, live they are extracted by two models.
      </p>
    </div>
  );
}
