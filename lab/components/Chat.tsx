"use client";

import { useEffect, useRef, useState } from "react";

// Our own agent chat. The page only shows what /api/chat says; the server runs the same tools and
// guard as outside agents. The chat has no tool to place an order or pay — that stays on /account.

type Card = {
  n: number;
  title: string;
  url: string;
  store: string;
  price: number | null;
  currency: string | null;
  from?: boolean;
  fits: boolean | null;
  good: string[];
  bad: string[];
};
type Msg = { role: "user" | "assistant"; content: string; cards?: Card[] };
type State = { request?: string; results?: string[]; shown?: number };

const KEY = "asasked-chat";
const EXAMPLES = ["black patent shoes size 42 under $500", "inflatable tent", "which stores can you search?"];

const money = (p: number | null, c: string | null) =>
  typeof p !== "number" ? "Price on the store's site" : c && c !== "USD" ? `${p} ${c}` : `$${p}`;

// Links in replies: our own pages open here, store pages in a new tab.
function Text({ s }: { s: string }) {
  const parts = s.split(/(https?:\/\/[^\s,]+[^\s,.])/g);
  return (
    <>
      {parts.map((x, i) => {
        if (!/^https?:\/\//.test(x)) return <span key={i}>{x}</span>;
        let href = x;
        let own = false;
        try {
          const u = new URL(x);
          own = u.origin === location.origin || u.hostname === "lab.asasked.dev";
          if (own) href = u.pathname + u.search + u.hash;
        } catch {}
        return (
          <a key={i} href={href} className="link break-all" {...(own ? {} : { target: "_blank", rel: "nofollow noopener noreferrer" })}>
            {own ? href : x}
          </a>
        );
      })}
    </>
  );
}

function ResultCard({ c }: { c: Card }) {
  return (
    <li className="min-w-0 rounded-xl border border-line bg-paper p-3">
      <div className="flex items-start gap-3">
        <span className="meta mt-0.5 grid size-6 shrink-0 place-items-center rounded-full border border-line text-[11px]">{c.n}</span>
        <div className="min-w-0 flex-1">
          <a href={c.url} target="_blank" rel="nofollow noopener noreferrer" className="line-clamp-2 text-sm font-medium leading-snug hover:underline">
            {c.title}
          </a>
          <p className="mt-0.5 text-sm">
            <span className="font-semibold">
              {c.from && typeof c.price === "number" ? "from " : ""}
              {money(c.price, c.currency)}
            </span>
            <span className="text-muted"> · {c.store}</span>
          </p>
          {c.fits === true && (
            <p className="mt-1.5 rounded-lg bg-pass/10 px-2 py-1 text-[12px] leading-snug text-pass">
              <span className="font-semibold">Fits</span>
              {c.good.length ? `: ${c.good.join(" · ")}` : ""}
            </p>
          )}
          {c.fits === false && (
            <p className="mt-1.5 rounded-lg bg-[#c98a12]/10 px-2 py-1 text-[12px] leading-snug text-[#9a6a0c]">
              <span className="font-semibold">Differs</span>: {c.bad.join(" · ")}
            </p>
          )}
        </div>
      </div>
    </li>
  );
}

// After 10 s "Looking…" becomes a note with a stopwatch, so a slow model doesn't look like a hang.
function Waiting() {
  const [sec, setSec] = useState(0);
  useEffect(() => {
    const t0 = Date.now();
    const id = setInterval(() => setSec(Math.floor((Date.now() - t0) / 1000)), 1000);
    return () => clearInterval(id);
  }, []);
  return (
    <li className="meta self-start" aria-live="polite">
      {sec < 10 ? "Looking…" : `Still looking, this can take up to a minute · ${sec} s`}
    </li>
  );
}

export function Chat() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [state, setState] = useState<State>({});
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [me, setMe] = useState<string | null | undefined>(undefined);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // The conversation lives only in this tab; nothing is kept on the server.
    try {
      const saved = JSON.parse(sessionStorage.getItem(KEY) ?? "null");
      if (saved?.msgs) {
        setMsgs(saved.msgs);
        setState(saved.state ?? {});
      }
    } catch {}
    fetch("/api/me", { credentials: "same-origin" })
      .then((r) => r.json())
      .then((j) => setMe(j?.address ?? null))
      .catch(() => setMe(null));
  }, []);

  useEffect(() => {
    try {
      sessionStorage.setItem(KEY, JSON.stringify({ msgs: msgs.slice(-30), state }));
    } catch {}
    if (msgs.length) end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [msgs, state]);

  async function ask(text: string) {
    const content = text.trim();
    if (!content || busy) return;
    const next: Msg[] = [...msgs, { role: "user", content }];
    setMsgs(next);
    setQ("");
    setBusy(true);
    try {
      const r = await fetch("/api/chat", {
        method: "POST",
        credentials: "same-origin",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ messages: next.map(({ role, content }) => ({ role, content })), state }),
      });
      const j = await r.json().catch(() => null);
      const reply =
        r.status === 429
          ? "Too many messages in a minute. Wait a little and try again."
          : (j?.reply ?? j?.error ?? "Something went wrong. Try again.");
      setMsgs([...next, { role: "assistant", content: reply, cards: j?.cards ?? [] }]);
      if (r.ok && j?.state) setState(j.state);
    } catch {
      setMsgs([...next, { role: "assistant", content: "Could not reach the server. Try again." }]);
    } finally {
      setBusy(false);
    }
  }

  function clear() {
    setMsgs([]);
    setState({});
  }

  const short = (a: string) => `${a.slice(0, 4)}…${a.slice(-4)}`;

  return (
    <section className="mt-8">
      <p className="meta flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="flex items-center gap-1.5">
          <span aria-hidden className={me ? "text-pass" : "text-faint"}>
            ●
          </span>
          {me === undefined ? "Checking sign-in…" : me ? `Signed in as ${short(me)}` : "Not signed in: search and details only"}
        </span>
        {!me && me !== undefined && (
          <a href="/account" className="link -my-2.5 py-2.5 text-ink">
            Sign in with your wallet
          </a>
        )}
        {msgs.length > 0 && (
          <button type="button" onClick={clear} className="link -my-2.5 ml-auto py-2.5 text-ink">
            Clear chat
          </button>
        )}
      </p>

      <div className="mt-3 rounded-2xl border border-line bg-panel">
        <ol aria-live="polite" className="flex min-h-[260px] flex-col gap-4 p-4 sm:p-5">
          {msgs.length === 0 && (
            <li className="text-sm text-muted">
              <p>Tell me what you are looking for. I search the catalog and check each result against your size, colour and budget.</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {EXAMPLES.map((e) => (
                  <button
                    key={e}
                    type="button"
                    onClick={() => ask(e)}
                    className="rounded-full border border-line bg-paper px-3 py-1.5 text-left text-sm text-ink hover:border-ink"
                  >
                    {e}
                  </button>
                ))}
              </div>
            </li>
          )}
          {msgs.map((m, i) =>
            m.role === "user" ? (
              <li key={i} className="max-w-[85%] self-end whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-ink px-3.5 py-2 text-sm text-paper">
                {m.content}
              </li>
            ) : (
              <li key={i} className="min-w-0 max-w-full self-start sm:max-w-[92%]">
                <p className="whitespace-pre-wrap break-words text-sm leading-relaxed">
                  <Text s={m.content} />
                </p>
                {m.cards && m.cards.length > 0 && (
                  <ul className="mt-2 grid gap-2">
                    {m.cards.map((c) => (
                      <ResultCard key={`${i}-${c.n}`} c={c} />
                    ))}
                  </ul>
                )}
              </li>
            ),
          )}
          {busy && <Waiting />}
        </ol>
        <div ref={end} />
        <form
          onSubmit={(e) => {
            e.preventDefault();
            ask(q);
          }}
          className="flex items-center gap-2 border-t border-line p-2 sm:p-3"
        >
          <input
            type="text"
            aria-label="Message"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            maxLength={500}
            placeholder={msgs.length ? "save 1, details 2, more…" : "black loafers size 42 under $500"}
            enterKeyHint="send"
            className="h-11 min-w-0 flex-1 rounded-full bg-paper px-4 text-base text-ink outline-none placeholder:text-faint focus:ring-1 focus:ring-ink sm:text-sm"
          />
          <button
            type="submit"
            aria-label="Send"
            disabled={!q.trim() || busy}
            className="grid size-11 shrink-0 place-items-center rounded-full bg-signal text-white disabled:opacity-40"
          >
            <svg viewBox="0 0 16 16" className="size-4" aria-hidden fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M8 13V3M4 7l4-4 4 4" />
            </svg>
          </button>
        </form>
      </div>
    </section>
  );
}
