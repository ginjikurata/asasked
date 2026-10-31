"use client";

import { useState } from "react";

type Item = { sku: string; name: string; qty: number; price: string; merchant: string; returns: string; delivery_days: number };
type Heard = { k: string; v: string; soft: boolean; disputed: boolean };
type Step = { k: "agent" | "asked you" | "you"; v: string };
type Run = {
  request: string;
  agent: string;
  today: string;
  conversation: string;
  can_answer: boolean;
  answers_left: number;
  outcome: "bought" | "guard_asked" | "agent_asked" | "declined" | "nothing" | "error";
  question: string | null;
  heard: Heard[] | null;
  heard_error: string | null;
  steps: Step[];
  cart: Item[];
  guard: { decision: string; reasons: string[]; notes: string[] } | null;
  suggestions: Item[];
  final_text: string;
  error: string;
  log: { tool: string; args: unknown; result: unknown }[];
};

const MAX = 300;
const EXAMPLES = [
  "White Wilson Clash 100, grip 4 3/8 — has to arrive by Friday",
  "Three cans of balls, the cheapest you've got, but I want to be able to return them",
  "Any racket for a beginner, just not Babolat, under $150",
];

const STAMP: Record<Run["outcome"], { text: string; tone: string }> = {
  bought: { text: "paid", tone: "text-pass" },
  guard_asked: { text: "ask", tone: "text-signal" },
  agent_asked: { text: "asked", tone: "text-muted" },
  declined: { text: "declined", tone: "text-signal" },
  nothing: { text: "no order", tone: "text-muted" },
  error: { text: "error", tone: "text-muted" },
};

function itemLine(it: Item) {
  return `${it.qty} × ${it.name} · ${it.merchant} · ${it.price} · ${it.returns} · ${it.delivery_days}d delivery`;
}

function Row({ k, children, tone }: { k: string; children: React.ReactNode; tone?: string }) {
  return (
    <div className="grid grid-cols-[92px_1fr] gap-3 md:grid-cols-[100px_1fr]">
      <dt className="text-faint">{k}</dt>
      <dd className={tone ?? ""}>{children}</dd>
    </div>
  );
}

function verdict(run: Run): { k: string; v: string; tone: string } {
  switch (run.outcome) {
    case "bought":
      return { k: "guard", v: "proceed — the order matches your words, paid", tone: "text-pass" };
    case "guard_asked":
      return { k: "guard", v: "ask — payment stopped until you answer", tone: "font-medium text-signal" };
    case "agent_asked":
      return {
        k: "agent",
        v: run.can_answer ? "waiting for your answer" : "stopped to ask you a question",
        tone: "text-muted",
      };
    case "declined":
      return { k: "VI", v: "payment declined: outside the limits you signed", tone: "text-signal" };
    case "nothing":
      return { k: "agent", v: "bought nothing", tone: "text-muted" };
    default:
      return { k: "error", v: run.error || "the run failed", tone: "text-muted" };
  }
}

export function LiveTry() {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [open, setOpen] = useState<"right" | "log" | null>(null);
  const [reply, setReply] = useState("");

  // A new request starts a run; an answer continues the paused one, which stays on screen.
  async function submit(request: string, answering?: string) {
    const r = request.trim();
    if (!r || busy) return;
    setBusy(true);
    setError(null);
    if (!answering) setRun(null);
    setOpen(null);
    try {
      const res = await fetch("/api/try", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(answering ? { conversation: answering, answer: r } : { request: r }),
      });
      const data = await res.json().catch(() => ({ error: "The live demo is offline right now." }));
      if (!res.ok) setError(data.error ?? "Something went wrong.");
      else {
        setRun(data as Run);
        setReply("");
      }
    } catch {
      setError("The live demo is offline right now.");
    } finally {
      setBusy(false);
    }
  }

  const v = run && verdict(run);
  const question = run?.question?.trim();

  return (
    <div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit(text);
        }}
        className="rounded-lg border border-line bg-paper p-3 focus-within:border-ink"
      >
        <label htmlFor="live-request" className="sr-only">
          Your request
        </label>
        <textarea
          id="live-request"
          value={text}
          maxLength={MAX}
          rows={2}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit(text);
            }
          }}
          placeholder="Ask the agent to buy something, the way you'd ask a person…"
          className="w-full resize-none bg-transparent font-mono text-[14px] leading-relaxed outline-none placeholder:text-faint"
        />
        <div className="mt-2 flex items-center justify-between gap-3">
          <span className="meta">
            {text.length}/{MAX} · tennis store only: rackets, shoes, balls, bags
          </span>
          <button
            type="submit"
            disabled={busy || !text.trim()}
            className="rounded-full bg-ink px-4 py-1.5 font-mono text-[12px] text-paper disabled:opacity-40"
          >
            {busy ? "running…" : "send to agent"}
          </button>
        </div>
      </form>

      <div className="mt-3 flex flex-wrap gap-2">
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            type="button"
            disabled={busy}
            onClick={() => {
              setText(ex);
              submit(ex);
            }}
            className="rounded-full border border-line px-3 py-1 text-left font-mono text-[12px] text-muted transition-colors hover:border-ink hover:text-ink disabled:opacity-40"
          >
            {ex}
          </button>
        ))}
      </div>

      {error && <p className="mt-4 font-mono text-[13px] text-signal">{error}</p>}

      {(busy || run) && (
        <div className="receipt relative mt-5" aria-live="polite">
          <div className="flex items-center justify-between gap-3 border-b border-dashed border-faint/50 px-4 py-2">
            <span className="meta">asasked · live run{run ? ` · ${run.agent}` : ""}</span>
            {run && (
              <span className="meta hidden sm:inline" title="The sandbox store's calendar is fixed, so delivery deadlines stay checkable">
                store calendar (fixed): {run.today}
              </span>
            )}
          </div>
          <dl className="min-h-[200px] space-y-1.5 p-4 pb-16 font-mono text-[12.5px] leading-relaxed md:text-[13px]">
            {busy && !run && (
              <Row k="agent">
                shopping — searching, opening products, filling the cart. Takes one to three minutes{" "}
                <span className="inline-block h-4 w-2 animate-pulse bg-ink align-middle" />
              </Row>
            )}
            {run && (
              <>
                <Row k="$ request">“{run.request}”</Row>
                <Row k="guard heard" tone="text-muted">
                  {run.heard === null
                    ? "couldn't read the request — the guard will ask before any payment"
                    : run.heard.length === 0
                      ? "nothing specific: any tennis item would match"
                      : run.heard.map((h, i) => (
                          <span key={i}>
                            {i > 0 && " · "}
                            {h.k} <span className="text-ink">{h.v}</span>
                            {h.soft && " (not essential)"}
                            {h.disputed && " (models disagreed)"}
                          </span>
                        ))}
                </Row>
                {run.steps.map((s, i) => {
                  const first = s.k === "agent" && run.steps[i - 1]?.k !== "agent";
                  return s.k === "agent" ? (
                    <Row key={i} k={first ? "agent did" : ""} tone="text-muted">
                      {s.v}
                    </Row>
                  ) : (
                    <Row key={i} k={s.k === "you" ? "you" : "→ you"} tone={s.k === "you" ? "text-ink" : "text-muted"}>
                      <span className="whitespace-pre-line">{s.k === "you" ? `“${s.v}”` : s.v}</span>
                    </Row>
                  );
                })}
                {run.cart.map((it, i) => (
                  <Row key={it.sku} k={i === 0 ? "cart" : ""}>
                    {itemLine(it)}
                  </Row>
                ))}
                {v && (
                  <Row k={v.k} tone={v.tone}>
                    {v.v}
                  </Row>
                )}
                {run.guard?.reasons.map((r, i) => (
                  <Row key={`r${i}`} k="" tone="text-muted">
                    - {r}
                  </Row>
                ))}
                {run.guard?.notes.map((r, i) => (
                  <Row key={`n${i}`} k="" tone="text-faint">
                    note: {r}
                  </Row>
                ))}
                {question && (
                  <Row k="→ you" tone="text-ink">
                    <span className="whitespace-pre-line">{question}</span>
                  </Row>
                )}
                {busy && (
                  <Row k="agent">
                    continuing with your answer{" "}
                    <span className="inline-block h-4 w-2 animate-pulse bg-ink align-middle" />
                  </Row>
                )}
                {question && run.can_answer && !busy && (
                  <Row k="you">
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        submit(reply, run.conversation);
                      }}
                      className="flex items-center gap-2 border-b border-ink/40 focus-within:border-ink"
                    >
                      <label htmlFor="live-reply" className="sr-only">
                        Your answer
                      </label>
                      <input
                        id="live-reply"
                        value={reply}
                        maxLength={MAX}
                        autoFocus
                        onChange={(e) => setReply(e.target.value)}
                        placeholder="answer the agent…"
                        className="min-w-0 flex-1 bg-transparent py-0.5 outline-none placeholder:text-faint"
                      />
                      <button type="submit" disabled={!reply.trim()} className="text-ink disabled:opacity-40">
                        reply ↵
                      </button>
                    </form>
                  </Row>
                )}
                {question && !run.can_answer && (
                  <Row k="" tone="text-faint">
                    {run.answers_left > 0
                      ? "this conversation has closed — send a new request"
                      : "that's the last question this demo answers — send a new request"}
                  </Row>
                )}
                {run.outcome !== "guard_asked" && run.final_text && (
                  <Row k="agent said" tone="text-muted">
                    <span className="whitespace-pre-line">{run.final_text.replace(/<think>[\s\S]*?<\/think>/g, "").trim()}</span>
                  </Row>
                )}
              </>
            )}
          </dl>
          {run && !busy && (
            <span key={`${run.conversation}-${run.steps.length}`} className={`stamp absolute bottom-8 right-5 ${STAMP[run.outcome].tone}`}>
              {STAMP[run.outcome].text}
            </span>
          )}
        </div>
      )}

      {run && (
        <>
          <div className="mt-3 flex flex-wrap gap-2 font-mono text-[12px]">
            {(
              [
                ["right", "what fits your words"],
                ["log", "full agent log"],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                aria-expanded={open === key}
                onClick={() => setOpen(open === key ? null : key)}
                className={`rounded-full border px-3 py-1 transition-colors ${
                  open === key ? "border-ink bg-ink text-paper" : "border-line text-muted hover:border-ink hover:text-ink"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          {open === "right" && (
            <div className="mt-3 rounded-lg border border-line p-4 font-mono text-[12.5px] leading-relaxed">
              {run.suggestions.length ? (
                <>
                  <p className="text-faint">The guard would let these through without a question, cheapest first:</p>
                  <ul className="mt-2 space-y-1">
                    {run.suggestions.map((it) => (
                      <li key={it.sku}>{itemLine(it)}</li>
                    ))}
                  </ul>
                </>
              ) : (
                <p className="text-muted">
                  Nothing to show: either the request named no details to match against, it asked for several items at
                  once, or nothing in the store fits all of them.
                </p>
              )}
            </div>
          )}
          {open === "log" && (
            <pre className="mt-3 max-h-[420px] overflow-auto rounded-lg border border-line bg-panel p-4 font-mono text-[11.5px] leading-relaxed">
              {run.log
                .map((c) => `→ ${c.tool} ${JSON.stringify(c.args)}\n← ${JSON.stringify(c.result, null, 1)}`)
                .join("\n\n")}
            </pre>
          )}
        </>
      )}

      <p className="meta mt-3">
        A real model ({run?.agent ?? "deepseek-v4-flash"}) shops in the sandbox store; the payment is checked by
        Verifiable Intent, the guard stands in front of it. No money moves. When the agent or the guard needs your
        answer, the run pauses and you can reply right here. Up to 5 requests a day — a request where the agent
        didn&apos;t shop (a plain “hi”) doesn&apos;t count; answers don&apos;t count. What you type goes to AI model
        providers and isn&apos;t stored; see the{" "}
        <a href="/privacy" className="link">
          privacy policy
        </a>
        .
      </p>
    </div>
  );
}
