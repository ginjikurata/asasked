"use client";

// The account page: sign in with a wallet on the lab server, keep sizes and budget, give your own
// agent access over MCP, review the carts it saved, and place orders at Bottega Senatore yourself.
// Placing sends the unlocked address to our server for that one request only. Paying is always your own wallet.
import { useEffect, useRef, useState } from "react";
import { EMPTY, LockError, open, seal, signForLock, type Address, type Box } from "@/lib/addressBox";
import { findWallets, forget, getSession, onWalletChange, short, signIn, signOut, type WalletChoice } from "@/lib/wallet";

type Prefs = { sizes?: Record<string, string>; budget?: number; stores?: string[]; crypto_only?: boolean };
type Agent = { id: string; name: string; scopes: string[]; created: number; expires: number; last_used: number | null; revoked: number | null };
type Item = {
  url: string;
  title: string;
  store: string;
  option: string | null;
  price: number | null;
  currency: string | null;
  quantity: number;
  check: { fits: boolean; good: string[]; bad: string[] };
};
type Cart = { id: string; agent: string | null; request: string; items: Item[]; created: number };
type Line = { ok: boolean | null; text: string };
type Snap = {
  items: { id: number; name: string; option: string; quantity: number; price: number; total: number }[];
  currency: string;
  subtotal: number;
  shipping: number;
  tax: number;
  total: number;
  total_minor: string;
  shipping_name: string | null;
};
type Order = {
  id: string;
  agent: string | null;
  request: string;
  items: { url: string; title: string; option: string | null; quantity: number }[];
  fit: { lines: Line[]; verdict: Verdict } | null;
  snap: Snap | null;
  status: "prepared" | "placing" | "placed" | "failed" | "canceled" | "expired";
  order_id: string | null;
  invoice_url: string | null;
  invoice: { lines: Line[]; verdict: Verdict; pay: { address: string; usdc: number } | null; usdc: number | null } | null;
  note: string | null;
  created: number;
  expires: number;
};
type Verdict = "pass" | "check" | "stop";
type Profile = { address: string; prefs: Prefs; history: { q: string }[]; agents: Agent[]; carts: Cart[]; orders?: Order[] };
type Grant = { id: string; name: string; token: string; mcp_url: string; expires: number };
type Store = { name: string; domain: string };

const SCOPES: Record<string, string> = {
  read_prefs: "Read your sizes, budget and favourite stores",
  save_cart: "Save carts and prepare orders here for you to review. You place and pay yourself",
};
const SIZE_KEYS = ["shoes", "clothing", "jeans", "ring"];

class ApiError extends Error {
  constructor(public status: number, message: string, public body: unknown = null) {
    super(message);
  }
}

async function api<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const r = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: body === undefined ? {} : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const j = await r.json().catch(() => null);
  if (!r.ok) throw new ApiError(r.status, j?.error ?? "Something went wrong. Try again.", j);
  return j as T;
}

const b64 = (u: Uint8Array) => btoa(String.fromCharCode(...u));
const day = (t: number) => new Date(t).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
const money = (n: number | null, c: string | null) => (n === null ? "" : c && c !== "USD" ? `${n} ${c}` : `$${n}`);
const why = (e: unknown) => {
  const msg = e instanceof Error ? e.message : "";
  return /reject|denied|cancel/i.test(msg) ? "You cancelled the request in your wallet." : msg || "The wallet did not sign.";
};

// Errors from our own server (or no connection to it), for buttons that do not use the wallet.
const apiWhy = (e: unknown) => (e instanceof ApiError ? e.message : "Could not reach the server. Try again.");

const card = "rounded-2xl border border-line bg-panel p-4 sm:p-5";
const button = "h-10 rounded-full bg-ink px-4 text-sm text-paper hover:bg-ink/85 disabled:opacity-50";
const quiet = "h-10 rounded-full border border-line px-4 text-sm hover:border-ink disabled:opacity-50";
const field = "h-10 rounded-xl border border-line bg-paper px-3 text-sm outline-none focus:border-ink";

export function Account({ stores }: { stores: Store[] }) {
  const [state, setState] = useState<"loading" | "offline" | "out" | "in">("loading");
  const [profile, setProfile] = useState<Profile | null>(null);
  const [wallets, setWallets] = useState<WalletChoice[]>([]);
  const walletName = useRef("");

  async function load() {
    const p = await api<Profile>("/api/profile");
    const s = getSession();
    if (s?.address === p.address && s.wallet !== "a wallet") walletName.current ||= s.wallet;
    setProfile(p);
    setState("in");
    return p;
  }

  useEffect(() => {
    const stop = findWallets(setWallets);
    (async () => {
      try {
        await api("/api/health");
      } catch {
        return setState("offline");
      }
      try {
        // Ask who is signed in first: /api/profile answers 401 to visitors, which shows as a console error.
        const me = await fetch("/api/me", { credentials: "same-origin" }).then((r) => r.json()).catch(() => null);
        if (!me?.address) return setState("out");
        await load();
        const hash = location.hash.slice(1);
        if (hash) requestAnimationFrame(() => document.getElementById(hash)?.scrollIntoView());
      } catch (e) {
        setState(e instanceof ApiError && e.status === 401 ? "out" : "offline");
      }
    })();
    // Signing in or out from the wallet menu updates this page too.
    const stopSync = onWalletChange(() => {
      const s = getSession();
      if (s?.server) load().catch(() => setState("out"));
      else setState((st) => (st === "in" ? "out" : st));
    });
    return () => {
      stop();
      stopSync();
    };
  }, []);

  // A wallet signature for this account: connects the wallet the person signed in with and checks it is the same address.
  async function signWith(text: string, address?: string) {
    const w = wallets.find((x) => x.name === walletName.current) ?? wallets[0];
    if (!w) throw new Error("No Solana wallet found in this browser.");
    const acct = await w.connect();
    if (address && acct.address !== address) throw new Error(`Switch your wallet to ${short(address)} and try again.`);
    walletName.current = w.name;
    return { address: acct.address, signature: b64(await acct.sign(new TextEncoder().encode(text))) };
  }

  // The key for the delivery address: a signature of the fixed lock text from the signed-in wallet.
  async function lockKey(address: string, check: boolean) {
    const w = wallets.find((x) => x.name === walletName.current) ?? wallets[0];
    if (!w) throw new Error("No Solana wallet found in this browser.");
    const acct = await w.connect();
    if (acct.address !== address) throw new Error(`Switch your wallet to ${short(address)} and try again.`);
    walletName.current = w.name;
    return signForLock(address, acct.sign, check);
  }

  if (state === "loading") return <p className="mt-10 text-muted">Loading…</p>;
  if (state === "offline")
    return (
      <div className={`${card} mt-10`}>
        <h2 className="font-medium">Accounts are not open yet</h2>
        <p className="mt-1 text-muted">
          This part of the lab needs our server, and it is not running here. You can still search the catalog without an
          account, and the search history in the wallet menu stays in your browser.
        </p>
        <a href="/products" className="link mt-3 inline-block text-sm">
          Search products →
        </a>
      </div>
    );
  if (state === "out") return <SignIn wallets={wallets} walletName={walletName} onDone={load} />;
  if (!profile) return null;

  return (
    <div className="mt-10 flex flex-col gap-10">
      <section>
        <p className="meta">Signed in with {walletName.current || "a wallet"}</p>
        <p className="mt-0.5 break-all font-mono text-[12px]">{profile.address}</p>
        <button
          type="button"
          className="link mt-2 text-sm"
          onClick={async () => {
            await signOut();
            setProfile(null);
            setState("out");
          }}
        >
          Sign out
        </button>
      </section>
      <PrefsForm prefs={profile.prefs} stores={stores} onSaved={(prefs) => setProfile({ ...profile, prefs })} />
      <DeliveryAddress wallet={profile.address} lockKey={lockKey} />
      <Agents profile={profile} signWith={signWith} reload={load} />
      <Carts carts={profile.carts} reload={load} />
      <Orders orders={profile.orders ?? []} wallet={profile.address} lockKey={lockKey} reload={load} />
      <Stored history={profile.history.length} onDeleted={() => (forget(), setProfile(null), setState("out"))} />
    </div>
  );
}

function SignIn({ wallets, walletName, onDone }: { wallets: WalletChoice[]; walletName: { current: string }; onDone: () => Promise<unknown> }) {
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  async function go(w: WalletChoice) {
    setBusy(w.name);
    setError("");
    try {
      await signIn(w); // the same sign-in as the wallet menu, so the header knows too
      walletName.current = w.name;
      await onDone();
    } catch (e) {
      setError(why(e));
    } finally {
      setBusy("");
    }
  }

  return (
    <div className={`${card} mt-10 max-w-md`}>
      <h2 className="font-medium">Sign in with your wallet</h2>
      <p className="mt-1 text-sm leading-snug text-muted">
        Your wallet asks you to sign a short text. It is not a transaction: no fee, no money moves. We keep your wallet address
        and what you save here, nothing else.
      </p>
      {wallets.length ? (
        <ul className="mt-3 flex flex-col gap-2">
          {wallets.map((w) => (
            <li key={w.name}>
              <button
                type="button"
                disabled={Boolean(busy)}
                onClick={() => go(w)}
                className="flex h-10 w-full items-center gap-3 rounded-xl border border-line px-3 text-left text-sm hover:border-ink disabled:opacity-50"
              >
                {w.icon ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={w.icon} alt="" className="size-5 rounded" />
                ) : (
                  <span aria-hidden className="size-5 rounded bg-line" />
                )}
                <span className="flex-1">{w.name}</span>
                {busy === w.name && <span className="meta">Check your wallet…</span>}
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 rounded-xl bg-paper p-3 text-sm leading-snug">
          <span className="mb-2 block sm:hidden">
            On a phone, open this page inside your wallet app:{" "}
            <a
              href={`https://phantom.app/ul/browse/${encodeURIComponent("https://lab.asasked.dev/account")}?ref=${encodeURIComponent("https://lab.asasked.dev")}`}
              className="link"
            >
              Open in Phantom app
            </a>
            .
          </span>
          No Solana wallet found in this browser. Install{" "}
          <a href="https://phantom.com/download" target="_blank" rel="noopener noreferrer" className="link">
            Phantom
          </a>{" "}
          or{" "}
          <a href="https://solflare.com/download" target="_blank" rel="noopener noreferrer" className="link">
            Solflare
          </a>
          , then reload this page.
        </p>
      )}
      {error && <p className="mt-2 text-[12px] text-[#9a6a0c]">{error}</p>}
    </div>
  );
}

function Head({ title, note }: { title: string; note?: string }) {
  return (
    <div className="mb-3">
      <h2 className="text-[22px] font-semibold tracking-[-0.01em]">{title}</h2>
      {note && <p className="mt-1 text-sm text-muted">{note}</p>}
    </div>
  );
}

function PrefsForm({ prefs, stores, onSaved }: { prefs: Prefs; stores: Store[]; onSaved: (p: Prefs) => void }) {
  const [sizes, setSizes] = useState(() => {
    const rows = Object.entries(prefs.sizes ?? {}).map(([k, v]) => ({ k, v }));
    return rows.length ? rows : [{ k: "shoes", v: "" }];
  });
  const [budget, setBudget] = useState(prefs.budget === undefined ? "" : String(prefs.budget));
  const [fav, setFav] = useState<string[]>(prefs.stores ?? []);
  const [cryptoOnly, setCryptoOnly] = useState(Boolean(prefs.crypto_only));
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const name = (d: string) => stores.find((s) => s.domain === d)?.name ?? d;

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setNote("");
    const next: Prefs = {
      sizes: Object.fromEntries(sizes.map(({ k, v }) => [k.trim().toLowerCase(), v.trim()]).filter(([k, v]) => k && v)),
      stores: fav,
      crypto_only: cryptoOnly,
    };
    if (budget.trim()) next.budget = Number(budget);
    try {
      const r = await api<{ prefs: Prefs }>("/api/profile", "PUT", { prefs: next });
      onSaved(r.prefs);
      setNote("Saved.");
    } catch (err) {
      setNote(err instanceof Error ? err.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <Head title="Sizes and budget" note="Your agent reads these when you allow it, so you do not have to repeat them." />
      <form onSubmit={save} className={`${card} flex flex-col gap-5`}>
        <fieldset className="min-w-0">
          <legend className="text-sm font-medium">Sizes</legend>
          <p className="meta mt-0.5">A size, like 42, M or 7. No names or addresses.</p>
          <datalist id="size-keys">
            {SIZE_KEYS.map((k) => (
              <option key={k} value={k} />
            ))}
          </datalist>
          <ul className="mt-2 flex flex-col gap-2">
            {sizes.map((row, i) => (
              <li key={i} className="flex gap-2">
                <input
                  aria-label="What the size is for"
                  list="size-keys"
                  value={row.k}
                  maxLength={20}
                  onChange={(e) => setSizes(sizes.map((r, j) => (j === i ? { ...r, k: e.target.value } : r)))}
                  className={`${field} w-32 min-w-0 sm:w-40`}
                  placeholder="shoes"
                />
                <input
                  aria-label="Size"
                  value={row.v}
                  maxLength={20}
                  onChange={(e) => setSizes(sizes.map((r, j) => (j === i ? { ...r, v: e.target.value } : r)))}
                  className={`${field} min-w-0 flex-1`}
                  placeholder="42"
                />
                <button
                  type="button"
                  aria-label="Remove this size"
                  onClick={() => setSizes(sizes.filter((_, j) => j !== i))}
                  className="grid size-10 shrink-0 place-items-center rounded-full text-muted hover:bg-paper hover:text-ink"
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
          {sizes.length < 8 && (
            <button type="button" onClick={() => setSizes([...sizes, { k: "", v: "" }])} className="link mt-2 text-sm">
              Add a size
            </button>
          )}
        </fieldset>

        <label className="flex flex-col gap-1">
          <span className="text-sm font-medium">Usual budget, USD</span>
          <input
            type="number"
            min={0}
            max={1000000}
            inputMode="decimal"
            value={budget}
            onChange={(e) => setBudget(e.target.value)}
            className={`${field} w-40`}
            placeholder="500"
          />
        </label>

        <div>
          <label htmlFor="fav-store" className="text-sm font-medium">
            Favourite stores
          </label>
          {fav.length > 0 && (
            <ul className="mt-2 flex flex-wrap gap-2">
              {fav.map((d) => (
                <li key={d} className="flex h-8 items-center gap-1 rounded-full border border-line bg-paper pl-3 pr-1 text-sm">
                  {name(d)}
                  <button
                    type="button"
                    aria-label={`Remove ${name(d)}`}
                    onClick={() => setFav(fav.filter((x) => x !== d))}
                    className="grid size-6 place-items-center rounded-full text-muted hover:text-ink"
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          )}
          {fav.length < 20 && (
            <select
              id="fav-store"
              value=""
              onChange={(e) => e.target.value && setFav([...fav, e.target.value])}
              className={`${field} mt-2 w-full max-w-xs`}
            >
              <option value="">Add a store…</option>
              {stores
                .filter((s) => !fav.includes(s.domain))
                .map((s) => (
                  <option key={s.domain} value={s.domain}>
                    {s.name}
                  </option>
                ))}
            </select>
          )}
        </div>

        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" checked={cryptoOnly} onChange={(e) => setCryptoOnly(e.target.checked)} className="mt-0.5 size-4" />
          <span>Only suggest products I can pay for in crypto at checkout</span>
        </label>

        <div className="flex items-center gap-3">
          <button type="submit" disabled={busy} className={button}>
            Save
          </button>
          {note && <span className="text-sm text-muted">{note}</span>}
        </div>
      </form>
    </section>
  );
}

function Agents({
  profile,
  signWith,
  reload,
}: {
  profile: Profile;
  signWith: (text: string, address?: string) => Promise<{ signature: string }>;
  reload: () => Promise<unknown>;
}) {
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState<string[]>(["read_prefs", "save_cart"]);
  const [days, setDays] = useState(30);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [grant, setGrant] = useState<Grant | null>(null);
  const [listError, setListError] = useState("");
  const live = profile.agents.filter((a) => !a.revoked && a.expires > Date.now());

  async function give(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const c = await api<{ nonce: string; text: string }>("/api/agents/challenge", "POST", { name, scopes, days });
      const { signature } = await signWith(c.text, profile.address);
      setGrant(await api<Grant>("/api/agents", "POST", { nonce: c.nonce, signature }));
      setName("");
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : why(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <Head
        title="Your agent"
        note="Connect Claude, ChatGPT or another agent that supports MCP. It searches the catalog, checks products against what you asked, saves carts here and can prepare an order at Bottega Senatore. It cannot place an order, see your address or pay."
      />

      {grant && <Connect grant={grant} onClose={() => setGrant(null)} />}

      <form onSubmit={give} className={`${card} flex flex-col gap-4`}>
        <label className="flex flex-col gap-1">
          <span className="text-sm font-medium">Agent name</span>
          <input
            required
            maxLength={40}
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={`${field} max-w-xs`}
            placeholder="Claude on my laptop"
          />
        </label>
        <fieldset className="flex min-w-0 flex-col gap-2">
          <legend className="text-sm font-medium">It may</legend>
          {Object.entries(SCOPES).map(([k, label]) => (
            <label key={k} className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                checked={scopes.includes(k)}
                onChange={(e) => setScopes(e.target.checked ? [...scopes, k] : scopes.filter((s) => s !== k))}
                className="mt-0.5 size-4"
              />
              {label}
            </label>
          ))}
          <p className="meta">It can always search the open catalog, with or without access.</p>
        </fieldset>
        <label className="flex flex-col gap-1">
          <span className="text-sm font-medium">For</span>
          <select value={days} onChange={(e) => setDays(Number(e.target.value))} className={`${field} w-40`}>
            <option value={7}>7 days</option>
            <option value={30}>30 days</option>
            <option value={90}>90 days</option>
          </select>
        </label>
        <div>
          <button type="submit" disabled={busy || !scopes.length || !name.trim()} className={button}>
            {busy ? "Check your wallet…" : "Give access"}
          </button>
          <p className="meta mt-2">Your wallet signs a text naming the agent and what it may do. No fee, no money moves.</p>
          {error && <p className="mt-2 text-[12px] text-[#9a6a0c]">{error}</p>}
        </div>
      </form>

      {profile.agents.length > 0 && (
        <ul className="mt-4 overflow-hidden rounded-xl border border-line">
          {profile.agents.map((a) => {
            const on = !a.revoked && a.expires > Date.now();
            return (
              <li key={a.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line px-4 py-3 first:border-t-0">
                <span className="min-w-0 flex-1">
                  <span className={`block truncate font-medium ${on ? "" : "text-muted line-through"}`}>{a.name}</span>
                  <span className="meta block">
                    {a.scopes.map((s) => s.replace("_", " ")).join(" · ")} ·{" "}
                    {a.revoked ? `access taken ${day(a.revoked)}` : on ? `until ${day(a.expires)}` : `ended ${day(a.expires)}`}
                    {a.last_used ? ` · last used ${day(a.last_used)}` : " · not used yet"}
                  </span>
                </span>
                {on && (
                  <button
                    type="button"
                    className="link text-sm"
                    onClick={async () => {
                      setListError("");
                      try {
                        await api(`/api/agents/${a.id}`, "DELETE");
                        await reload();
                      } catch (err) {
                        setListError(`Access was not taken: ${apiWhy(err)}`);
                      }
                    }}
                  >
                    Take access
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {listError && (
        <p role="alert" className="mt-2 text-[12px] text-[#9a6a0c]">
          {listError}
        </p>
      )}
      {live.length > 0 && <p className="meta mt-2">{live.length} with access now.</p>}
    </section>
  );
}

function Copy({ text, label }: { text: string; label: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setDone(true);
          setTimeout(() => setDone(false), 1500);
        } catch {}
      }}
      className="link shrink-0 text-sm"
    >
      {done ? "Copied" : label}
    </button>
  );
}

function Block({ code }: { code: string }) {
  return (
    <div className="mt-2 rounded-xl border border-line bg-paper">
      <pre className="overflow-x-auto p-3 font-mono text-[12px] leading-relaxed">{code}</pre>
      <div className="border-t border-line px-3 py-2 text-right">
        <Copy text={code} label="Copy" />
      </div>
    </div>
  );
}

function Connect({ grant, onClose }: { grant: Grant; onClose: () => void }) {
  const cli = `claude mcp add --transport http asasked-lab ${grant.mcp_url} \\\n  --header "Authorization: Bearer ${grant.token}"`;
  const json = JSON.stringify(
    { mcpServers: { "asasked-lab": { type: "http", url: grant.mcp_url, headers: { Authorization: `Bearer ${grant.token}` } } } },
    null,
    2,
  );
  return (
    <div role="status" className="mb-4 rounded-2xl border border-signal/30 bg-signal-soft p-4 sm:p-5">
      <h3 className="font-medium">Access for “{grant.name}” is ready</h3>
      <p className="mt-1 text-sm">
        Copy the token now. We keep only a fingerprint of it, so it cannot be shown again. Anyone with the token can use this
        access until {day(grant.expires)} or until you take it.
      </p>
      <div className="mt-3 flex items-center gap-3 rounded-xl border border-line bg-panel p-3">
        <code className="min-w-0 flex-1 break-all font-mono text-[12px]">{grant.token}</code>
        <Copy text={grant.token} label="Copy token" />
      </div>
      <h4 className="mt-4 text-sm font-medium">Claude Code</h4>
      <Block code={cli} />
      <h4 className="mt-4 text-sm font-medium">Other agents (MCP config)</h4>
      <Block code={json} />
      <p className="meta mt-3">
        Server: {grant.mcp_url} · header Authorization: Bearer &lt;token&gt;. Then ask your agent, for example, “find black
        loafers in my size under my budget and save a cart”.
      </p>
      <button type="button" onClick={onClose} className={`${quiet} mt-4`}>
        I saved the token
      </button>
    </div>
  );
}

function Carts({ carts, reload }: { carts: Cart[]; reload: () => Promise<unknown> }) {
  const [error, setError] = useState<{ id: string; text: string } | null>(null);
  return (
    <section>
      <Head
        title="Saved carts"
        note={`What your agent picked for you. Check each item. At ${ORDER_STORE} you can prepare an order here; elsewhere, buy on the store's own site.`}
      />
      {carts.length === 0 ? (
        <p className={`${card} text-sm text-muted`}>Nothing yet. Carts your agent saves show up here.</p>
      ) : (
        <ul className="flex flex-col gap-4">
          {carts.map((c) => (
            <li key={c.id} id={`cart-${c.id}`} className={`${card} scroll-mt-20 target:border-ink`}>
              <div className="flex flex-wrap items-baseline justify-between gap-x-4">
                <h3 className="min-w-0 font-medium">“{c.request}”</h3>
                <span className="meta">
                  {c.agent ?? "Agent"} · {day(c.created)}
                </span>
              </div>
              <ul className="mt-3 flex flex-col divide-y divide-line">
                {c.items.map((it, i) => (
                  <li key={i} className="py-3 first:pt-0 last:pb-0">
                    <div className="flex flex-wrap items-baseline gap-x-3">
                      <a href={it.url} target="_blank" rel="noopener noreferrer nofollow" className="link min-w-0 flex-1 font-medium">
                        {it.title}
                      </a>
                      <span className="text-sm">
                        {money(it.price, it.currency)}
                        {it.quantity > 1 && ` × ${it.quantity}`}
                      </span>
                    </div>
                    <p className="meta">
                      {it.store}
                      {it.option && ` · ${it.option}`}
                    </p>
                    <p className={`mt-1 text-sm ${it.check.fits ? "text-pass" : "text-[#9a6a0c]"}`}>
                      {it.check.fits ? "Fits what you asked" : `Check: ${it.check.bad.join("; ")}`}
                      {it.check.fits && it.check.good.length > 0 && <span className="text-muted"> · {it.check.good.join(", ")}</span>}
                    </p>
                  </li>
                ))}
              </ul>
              {c.items.length > 0 && c.items.every((it) => it.store === ORDER_STORE) && <PrepareFromCart cart={c} reload={reload} />}
              <div className="mt-4 flex items-center justify-between gap-4 border-t border-line pt-3">
                <p className="meta">Not ordered. Prices and stock may change at the store.</p>
                <button
                  type="button"
                  className="link shrink-0 text-sm"
                  onClick={async () => {
                    setError(null);
                    try {
                      await api(`/api/carts/${c.id}`, "DELETE");
                      await reload();
                    } catch (err) {
                      setError({ id: c.id, text: `Not removed: ${apiWhy(err)}` });
                    }
                  }}
                >
                  Remove
                </button>
              </div>
              {error?.id === c.id && (
                <p role="alert" className="mt-2 text-[12px] text-[#9a6a0c]">
                  {error.text}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

const ORDER_STORE = "Bottega Senatore";
const VERDICT: Record<Verdict, { text: string; cls: string }> = {
  pass: { text: "Guard: all checks pass", cls: "text-pass" },
  check: { text: "Guard: check the lines marked ?", cls: "text-[#9a6a0c]" },
  stop: { text: "Guard: stop", cls: "text-signal-ink" },
};
const time = (t: number) => new Date(t).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
const cash = (n: number, c: string) => (c === "USD" || !c ? `$${n.toFixed(2)}` : `${n.toFixed(2)} ${c}`);

// Region only (country, state, postcode): enough for the store to price shipping. No street, no name.
function PrepareFromCart({ cart, reload }: { cart: Cart; reload: () => Promise<unknown> }) {
  const [openForm, setOpenForm] = useState(false);
  const [where, setWhere] = useState({ country: "", state: "", postcode: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function go(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const { order: o } = await api<{ order: Order }>("/api/orders/prepare", "POST", { cart_id: cart.id, where });
      await reload();
      requestAnimationFrame(() => document.getElementById(`order-${o.id}`)?.scrollIntoView({ behavior: "smooth" }));
      setOpenForm(false);
    } catch (err) {
      setError(apiWhy(err));
    } finally {
      setBusy(false);
    }
  }
  if (!openForm)
    return (
      <div className="mt-4">
        <button type="button" className={quiet} onClick={() => setOpenForm(true)}>
          Prepare order at {ORDER_STORE}
        </button>
      </div>
    );
  return (
    <form onSubmit={go} className="mt-4 flex flex-col gap-3 rounded-xl border border-line bg-paper p-3 text-sm">
      <p className="text-muted">
        Where it ships, for the shipping price. Only the region: your street and name go in later, when you place the order. Nothing is ordered yet.
      </p>
      <div className="grid grid-cols-3 gap-3">
        {(
          [
            ["country", "Country code", "country", 2],
            ["state", "State (optional)", "address-level1", 40],
            ["postcode", "Postal code", "postal-code", 20],
          ] as const
        ).map(([k, label, auto, max]) => (
          <label key={k} className="flex min-w-0 flex-col gap-1">
            <span className="font-medium">{label}</span>
            <input
              required={k === "country"}
              autoComplete={`shipping ${auto}`}
              maxLength={max}
              value={where[k]}
              onChange={(e) => setWhere({ ...where, [k]: k === "country" ? e.target.value.toUpperCase() : e.target.value })}
              className={`${field} min-w-0`}
              placeholder={k === "country" ? "US" : ""}
            />
          </label>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <button type="submit" className={button} disabled={busy || !/^[A-Za-z]{2}$/.test(where.country)}>
          {busy ? "Asking the store…" : "Prepare"}
        </button>
        <button type="button" className="link" onClick={() => setOpenForm(false)}>
          Not now
        </button>
      </div>
      {error && (
        <p role="alert" className="text-[12px] text-[#9a6a0c]">
          {error}
        </p>
      )}
    </form>
  );
}

function GuardLines({ lines, verdict }: { lines: Line[]; verdict: Verdict }) {
  return (
    <div className="mt-3">
      <p className={`text-sm font-medium ${VERDICT[verdict].cls}`}>{VERDICT[verdict].text}</p>
      <ul className="mt-1 flex flex-col gap-0.5 text-sm">
        {lines.map((l, i) => (
          <li key={i} className="flex gap-2">
            <span aria-hidden className={`w-4 shrink-0 text-center ${l.ok === true ? "text-pass" : l.ok === false ? "text-signal-ink" : "text-[#9a6a0c]"}`}>
              {l.ok === true ? "✓" : l.ok === false ? "✕" : "?"}
            </span>
            <span className="sr-only">{l.ok === true ? "Pass:" : l.ok === false ? "Fail:" : "Check:"}</span>
            <span className="min-w-0 [overflow-wrap:anywhere]">{l.text}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

const STATUS: Record<Order["status"], string> = {
  prepared: "Prepared, not ordered",
  placing: "Placing…",
  placed: "Ordered, not paid",
  failed: "Not ordered",
  canceled: "Canceled",
  expired: "Expired, not ordered",
};

function Orders({
  orders,
  wallet,
  lockKey,
  reload,
}: {
  orders: Order[];
  wallet: string;
  lockKey: (address: string, check: boolean) => Promise<Uint8Array>;
  reload: () => Promise<unknown>;
}) {
  const [busy, setBusy] = useState("");
  const [sure, setSure] = useState("");
  const [msg, setMsg] = useState<{ id: string; text: string } | null>(null);

  async function place(o: Order) {
    if (!o.snap) return;
    setBusy(o.id);
    setMsg(null);
    try {
      const saved = await api<{ box: Box | null }>("/api/address");
      if (!saved.box) throw new LockError("Add a delivery address above first.");
      // The address is unlocked here, sent in this one request and dropped from memory after.
      let address: Address | null = await open(saved.box, wallet, await lockKey(wallet, false));
      if (!/^[A-Za-z]{2}$/.test(address.country.trim()))
        throw new LockError("Change Country in your delivery address to a two-letter code, like US or DE, then try again.");
      const body = { address, total_minor: o.snap.total_minor };
      address = null;
      const { order: done } = await api<{ order: Order }>(`/api/orders/${o.id}/place`, "POST", body);
      await reload();
      if (done.status === "failed") setMsg({ id: o.id, text: done.note ?? "The store did not make the order." });
    } catch (e) {
      setMsg({ id: o.id, text: e instanceof ApiError || e instanceof LockError ? e.message : why(e) });
      await reload().catch(() => {});
    } finally {
      setBusy("");
      setSure("");
    }
  }

  async function drop(o: Order) {
    setBusy(o.id);
    setMsg(null);
    try {
      await api(`/api/orders/${o.id}`, "DELETE");
      await reload();
    } catch (e) {
      setMsg({ id: o.id, text: apiWhy(e) });
    } finally {
      setBusy("");
    }
  }

  return (
    <section id="orders">
      <Head
        title="Orders"
        note={`Prepared here from a saved cart at ${ORDER_STORE}. Placing makes an unpaid order at the store; you pay its BitPay invoice from your own wallet. We never hold your money.`}
      />
      {orders.length === 0 ? (
        <p className={`${card} text-sm text-muted`}>No orders. Prepare one from a saved {ORDER_STORE} cart, or let your agent prepare one.</p>
      ) : (
        <ul className="flex flex-col gap-4">
          {orders.map((o) => {
            const s = o.snap;
            const live = o.status === "prepared" && o.expires > Date.now();
            const blocked = o.fit?.verdict === "stop";
            return (
              <li key={o.id} id={`order-${o.id}`} className={`${card} scroll-mt-20 target:border-ink`}>
                <div className="flex flex-wrap items-baseline justify-between gap-x-4">
                  <h3 className="min-w-0 font-medium">“{o.request}”</h3>
                  <span className="meta">
                    {o.agent ?? "You"} · {day(o.created)}
                  </span>
                </div>
                <p className={`mt-1 text-sm font-medium ${o.status === "failed" ? "text-signal-ink" : ""}`}>
                  {live ? `${STATUS.prepared}. Place it by ${time(o.expires)}` : o.status === "prepared" ? STATUS.expired : STATUS[o.status]}
                  {o.order_id && ` · store order ${o.order_id}`}
                </p>
                {s && (
                  <div className="mt-3 text-sm">
                    <ul className="flex flex-col gap-1">
                      {s.items.map((it) => (
                        <li key={it.id} className="flex gap-3">
                          <span className="min-w-0 flex-1">
                            {it.name}
                            {it.option && <span className="text-muted"> · {it.option}</span>}
                            {it.quantity > 1 && ` × ${it.quantity}`}
                          </span>
                          <span>{cash(it.total, s.currency)}</span>
                        </li>
                      ))}
                    </ul>
                    <dl className="mt-2 grid grid-cols-[1fr_auto] gap-x-3 border-t border-line pt-2 text-muted">
                      <dt>Shipping{s.shipping_name ? ` (${s.shipping_name})` : ""}</dt>
                      <dd>{cash(s.shipping, s.currency)}</dd>
                      {s.tax > 0 && (
                        <>
                          <dt>Tax</dt>
                          <dd>{cash(s.tax, s.currency)}</dd>
                        </>
                      )}
                      <dt className="font-medium text-ink">Total at the store</dt>
                      <dd className="font-medium text-ink">{cash(s.total, s.currency)}</dd>
                    </dl>
                  </div>
                )}
                {o.fit && o.status !== "placed" && <GuardLines lines={o.fit.lines} verdict={o.fit.verdict} />}

                {o.status === "placed" && (
                  <div className="mt-4 rounded-xl border border-line bg-paper p-3 text-sm">
                    {o.invoice ? (
                      <>
                        <p className="font-medium">The invoice</p>
                        <GuardLines lines={o.invoice.lines} verdict={o.invoice.verdict} />
                        {o.invoice.verdict !== "stop" && o.invoice.pay && (
                          <div className="mt-3">
                            <p>
                              Your wallet will be asked to send <strong>{o.invoice.pay.usdc} USDC</strong> on Solana to
                            </p>
                            <p className="mt-0.5 break-all font-mono text-[12px]">{o.invoice.pay.address}</p>
                            <p className="mt-1 text-muted">If your wallet shows anything else, do not pay.</p>
                          </div>
                        )}
                        {o.invoice.verdict !== "stop" && o.invoice_url && (
                          <a href={o.invoice_url} target="_blank" rel="noopener noreferrer nofollow" className={`${button} mt-3 inline-flex items-center`}>
                            Pay on BitPay with your wallet
                          </a>
                        )}
                      </>
                    ) : (
                      <p className="text-muted">No invoice from the store.</p>
                    )}
                  </div>
                )}
                {o.note && <p className={`mt-3 text-sm ${o.invoice?.verdict === "stop" || o.status === "failed" ? "text-signal-ink" : "text-muted"}`}>{o.note}</p>}

                {msg?.id === o.id && (
                  <p role="alert" className="mt-3 text-sm text-[#9a6a0c]">
                    {msg.text}
                  </p>
                )}
                <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-line pt-3">
                  {live && !blocked && s && (
                    sure === o.id ? (
                      <>
                        <span className="text-sm">
                          Order for {cash(s.total, s.currency)} at {ORDER_STORE}? Your wallet unlocks the address, the store makes an unpaid order and sends the invoice.
                        </span>
                        <button type="button" className={button} disabled={busy !== ""} onClick={() => place(o)}>
                          {busy === o.id ? "Placing…" : "Place order"}
                        </button>
                        <button type="button" className="link text-sm" onClick={() => setSure("")}>
                          Not yet
                        </button>
                      </>
                    ) : (
                      <button type="button" className={button} disabled={busy !== ""} onClick={() => setSure(o.id)}>
                        Place order for {cash(s.total, s.currency)}
                      </button>
                    )
                  )}
                  {o.status !== "placing" && (
                    <button type="button" className="link text-sm" disabled={busy !== ""} onClick={() => drop(o)}>
                      {o.status === "prepared" ? "Cancel" : "Remove from this page"}
                    </button>
                  )}
                </div>
                {o.status === "placed" && (
                  <p className="meta mt-2">Removing it here does not cancel it at the store. Unpaid, the store may cancel it after a while.</p>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

const ADDRESS_FIELDS: { k: keyof Address; label: string; auto: string; wide?: boolean; type?: string }[] = [
  { k: "name", label: "Full name", auto: "name", wide: true },
  { k: "line1", label: "Address", auto: "address-line1", wide: true },
  { k: "line2", label: "Apartment, suite (optional)", auto: "address-line2", wide: true },
  { k: "city", label: "City", auto: "address-level2" },
  { k: "region", label: "State or region", auto: "address-level1" },
  { k: "postal", label: "Postal code", auto: "postal-code" },
  { k: "country", label: "Country code (US, DE, FR…)", auto: "country" },
  { k: "phone", label: "Phone", auto: "tel", type: "tel" },
  { k: "email", label: "Email", auto: "email", type: "email" },
];

function DeliveryAddress({ wallet, lockKey }: { wallet: string; lockKey: (address: string, check: boolean) => Promise<Uint8Array> }) {
  const [saved, setSaved] = useState<{ box: Box | null; updated: number | null } | null>(null);
  const [form, setForm] = useState<Address | null>(null);
  const sig = useRef<Uint8Array | null>(null);
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState("");
  const [sure, setSure] = useState(false);
  const [loadError, setLoadError] = useState("");

  // A failed load must not look like "no address": adding one then would replace the saved one.
  const load = () => {
    setLoadError("");
    api<{ box: Box | null; updated: number | null }>("/api/address").then(setSaved, (e) => setLoadError(apiWhy(e)));
  };
  useEffect(() => {
    load();
    return () => {
      sig.current = null;
    };
  }, []);

  const lock = () => {
    sig.current = null;
    setForm(null);
    setNote("");
  };
  const fail = (e: unknown) => setNote(e instanceof LockError || e instanceof ApiError ? e.message : why(e));

  async function unlock() {
    if (!saved) return;
    setBusy("unlock");
    setNote("");
    try {
      const s = await lockKey(wallet, !saved.box);
      setForm(saved.box ? await open(saved.box, wallet, s) : { ...EMPTY });
      sig.current = s;
    } catch (e) {
      fail(e);
    } finally {
      setBusy("");
    }
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!form || !sig.current) return;
    setBusy("save");
    setNote("");
    try {
      const box = await seal(form, wallet, sig.current);
      setSaved(await api("/api/address", "PUT", { box }));
      setNote("Saved, locked with your wallet.");
    } catch (err) {
      fail(err);
    } finally {
      setBusy("");
    }
  }

  async function remove() {
    setBusy("delete");
    setNote("");
    try {
      await api("/api/address", "DELETE");
      setSaved({ box: null, updated: null });
      setSure(false);
      lock();
      setNote("Deleted.");
    } catch (err) {
      fail(err);
    } finally {
      setBusy("");
    }
  }

  return (
    <section id="address">
      <Head
        title="Delivery address"
        note="Locked in this browser with a key from your wallet signature. Our server keeps only the locked copy and cannot read it. When you place an order, the unlocked address goes to the store through our server in that one request and is not kept. Agents never see it."
      />
      <div className={`${card} text-sm`}>
        {loadError ? (
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-[#9a6a0c]">Could not load your saved address. {loadError}</p>
            <button type="button" className={quiet} onClick={load}>
              Try again
            </button>
          </div>
        ) : !saved ? (
          <p className="text-muted">Loading…</p>
        ) : !form ? (
          <div className="flex flex-col gap-3">
            <p>
              {saved.box ? (
                <>A locked address is saved{saved.updated ? `, last changed ${day(saved.updated)}` : ""}. Sign with your wallet to see or change it.</>
              ) : (
                <>No address saved. Sign with your wallet to make the key, then add one. The wallet may ask twice the first time.</>
              )}
            </p>
            <div className="flex flex-wrap items-center gap-3">
              <button type="button" className={button} disabled={busy !== ""} onClick={unlock}>
                {busy === "unlock" ? "Waiting for the wallet…" : saved.box ? "Unlock with wallet" : "Add an address"}
              </button>
              {saved.box &&
                (sure ? (
                  <>
                    <span>Delete the saved address?</span>
                    <button type="button" className={quiet} disabled={busy !== ""} onClick={remove}>
                      Delete
                    </button>
                    <button type="button" className="link" onClick={() => setSure(false)}>
                      Keep
                    </button>
                  </>
                ) : (
                  <button type="button" className="link" onClick={() => setSure(true)}>
                    Delete
                  </button>
                ))}
            </div>
          </div>
        ) : (
          <form onSubmit={save} className="flex flex-col gap-4">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {ADDRESS_FIELDS.map((f) => (
                <label key={f.k} className={`flex min-w-0 flex-col gap-1 ${f.wide ? "sm:col-span-2" : ""}`}>
                  <span className="font-medium">{f.label}</span>
                  <input
                    type={f.type ?? "text"}
                    autoComplete={`shipping ${f.auto}`}
                    maxLength={200}
                    value={form[f.k]}
                    onChange={(e) => setForm({ ...form, [f.k]: e.target.value })}
                    className={field}
                  />
                </label>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <button type="submit" className={button} disabled={busy !== ""}>
                {busy === "save" ? "Locking…" : "Save locked"}
              </button>
              <button type="button" className={quiet} onClick={lock}>
                Lock
              </button>
            </div>
          </form>
        )}
        {note && (
          <p className="mt-3 text-muted" role="status">
            {note}
          </p>
        )}
      </div>
    </section>
  );
}

function Stored({ history, onDeleted }: { history: number; onDeleted: () => void }) {
  const [sure, setSure] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <section>
      <Head title="What we keep" />
      <div className={`${card} text-sm`}>
        <ul className="list-disc pl-5 leading-relaxed">
          <li>Your wallet address.</li>
          <li>Sizes, budget and favourite stores you saved above.</li>
          <li>Your searches while signed in ({history} now).</li>
          <li>Agent names, what each may do, and a fingerprint of each token (not the token).</li>
          <li>Carts your agent saved.</li>
          <li>Orders you prepared: items, totals, the guard's checks and the store's order number. Not the address.</li>
          <li>Your delivery address, if you added one, locked with your wallet. We cannot read it.</li>
        </ul>
        <p className="mt-2 text-muted">Nothing else about you: no readable names, emails, phone numbers or addresses. We never hold your money or keys.</p>
        <div className="mt-4 border-t border-line pt-3">
          {sure ? (
            <div className="flex flex-wrap items-center gap-3">
              <span>Delete your profile, agent access, carts, orders and locked address? This cannot be undone. Orders already placed stay at the store.</span>
              <button
                type="button"
                className={button}
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  setError("");
                  try {
                    await api("/api/profile", "DELETE");
                    onDeleted();
                  } catch (err) {
                    // Nothing was deleted, so we stay signed in and say so.
                    setError(`Nothing was deleted: ${apiWhy(err)}`);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                {busy ? "Deleting…" : "Delete everything"}
              </button>
              <button type="button" className={quiet} onClick={() => setSure(false)}>
                Keep
              </button>
            </div>
          ) : (
            <button type="button" className="link" onClick={() => setSure(true)}>
              Delete everything
            </button>
          )}
          {error && (
            <p role="alert" className="mt-2 text-[12px] text-[#9a6a0c]">
              {error}
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
