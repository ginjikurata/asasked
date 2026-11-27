// Sign in with a Solana wallet by signing a short text. No transaction, no fee, no money moves.
// The search history stays in this browser's storage and is never sent to us. When the lab server
// is running, the same signature also signs in to the account (profile, agent access, saved carts).

export type Session = { address: string; wallet: string; at: string; server?: boolean };
export type Past = { q: string; at: string; fits?: number };

export type WalletChoice = { name: string; icon?: string; connect(): Promise<{ address: string; sign(msg: Uint8Array): Promise<Uint8Array> }> };

const SESSION = "asasked.session";
const HISTORY = (a: string) => `asasked.history.${a}`;
const EVENT = "asasked:wallet";
const MAX = 50;

// ---- storage (may be blocked: private windows, cleared site data) ----

function read<T>(key: string): T | null {
  try {
    const v = localStorage.getItem(key);
    return v ? (JSON.parse(v) as T) : null;
  } catch {
    return null;
  }
}
function write(key: string, v: unknown) {
  try {
    if (v === null) localStorage.removeItem(key);
    else localStorage.setItem(key, JSON.stringify(v));
  } catch {}
}

export const getSession = () => read<Session>(SESSION);
const changed = () => dispatchEvent(new Event(EVENT));
export function onWalletChange(fn: () => void) {
  addEventListener(EVENT, fn);
  addEventListener("storage", fn);
  return () => {
    removeEventListener(EVENT, fn);
    removeEventListener("storage", fn);
  };
}

// ---- the lab server (accounts). The static site works without it. ----

let open: Promise<boolean> | null = null;
export function serverOpen(): Promise<boolean> {
  open ??= fetch("/api/health", { credentials: "same-origin" })
    .then((r) => r.json())
    .then((j) => j?.ok === true)
    .catch(() => false);
  return open;
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, {
    method: "POST",
    credentials: "same-origin",
    headers: body === undefined ? {} : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const j = await r.json().catch(() => null);
  if (!r.ok) throw new Error(j?.error ?? "Something went wrong. Try again.");
  return j as T;
}

// Makes this browser agree with the server: a server sign-in made elsewhere on the site shows up
// here, and a server session that expired is no longer shown as one.
export async function syncServer() {
  if (!(await serverOpen())) return;
  try {
    const { address } = await (await fetch("/api/me", { credentials: "same-origin" })).json();
    const s = getSession();
    if (address && (s?.address !== address || !s?.server)) {
      write(SESSION, { address, wallet: s && s.address === address ? s.wallet : "a wallet", at: new Date().toISOString(), server: true });
      changed();
    } else if (!address && s?.server) {
      write(SESSION, { ...s, server: false });
      changed();
    }
  } catch {}
}

export async function signOut() {
  const s = getSession();
  write(SESSION, null);
  changed();
  if (s?.server) await post("/api/auth/logout").catch(() => {});
}

// After the account is deleted on the server: forget it here too, search history included.
export function forget() {
  const s = getSession();
  if (s) write(HISTORY(s.address), null);
  write(SESSION, null);
  changed();
}

export function getHistory(): Past[] {
  const s = getSession();
  return s ? (read<Past[]>(HISTORY(s.address)) ?? []) : [];
}

export function remember(q: string, fits?: number) {
  const s = getSession();
  if (!s || !q) return;
  const rest = getHistory().filter((h) => h.q.toLowerCase() !== q.toLowerCase());
  write(HISTORY(s.address), [{ q, at: new Date().toISOString(), fits }, ...rest].slice(0, MAX));
  changed();
}

export function clearHistory() {
  const s = getSession();
  if (s) write(HISTORY(s.address), null);
  changed();
}

// ---- base58 ----

const B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
function b58decode(text: string): Uint8Array {
  let n = BigInt(0);
  for (const c of text) {
    const i = B58.indexOf(c);
    if (i < 0) throw new Error("not base58");
    n = n * BigInt(58) + BigInt(i);
  }
  const out: number[] = [];
  while (n > BigInt(0)) {
    out.unshift(Number(n % BigInt(256)));
    n /= BigInt(256);
  }
  for (const c of text) {
    if (c !== "1") break;
    out.unshift(0);
  }
  return new Uint8Array(out);
}

export const short = (a: string) => `${a.slice(0, 4)}…${a.slice(-4)}`;

// ---- finding wallets: the Wallet Standard handshake, plus the older injected objects ----

type Std = { name: string; icon?: string; chains: readonly string[]; accounts: readonly { address: string; chains: readonly string[] }[]; features: Record<string, any> };

export function findWallets(onChange: (w: WalletChoice[]) => void): () => void {
  const std = new Map<string, Std>();
  const emit = () => {
    const list: WalletChoice[] = [];
    for (const w of std.values()) {
      if (!w.chains.some((c) => c.startsWith("solana:")) || !w.features["standard:connect"] || !w.features["solana:signMessage"]) continue;
      list.push({
        name: w.name,
        icon: w.icon,
        async connect() {
          let accounts = w.accounts;
          if (!accounts.length) accounts = (await w.features["standard:connect"].connect()).accounts;
          const account = accounts.find((a) => a.chains.some((c) => c.startsWith("solana:"))) ?? accounts[0];
          if (!account) throw new Error(`${w.name} gave no account`);
          return {
            address: account.address,
            async sign(message: Uint8Array) {
              const [r] = await w.features["solana:signMessage"].signMessage({ account, message });
              return r.signature as Uint8Array;
            },
          };
        },
      });
    }
    // Wallets too old for the standard still inject an object on window.
    const win = window as any;
    const legacy: [string, any][] = [
      ["Phantom", win.phantom?.solana],
      ["Solflare", win.solflare],
    ];
    for (const [name, p] of legacy) {
      if (!p?.signMessage || list.some((w) => w.name === name)) continue;
      list.push({
        name,
        async connect() {
          const r = await p.connect();
          const address = String((r?.publicKey ?? p.publicKey).toString());
          return {
            address,
            async sign(message: Uint8Array) {
              const s = await p.signMessage(message, "utf8");
              return (s?.signature ?? s) as Uint8Array;
            },
          };
        },
      });
    }
    onChange(list);
  };
  const register = (...ws: Std[]) => {
    for (const w of ws) std.set(w.name, w);
    emit();
    return () => {};
  };
  const onRegister = (e: Event) => (e as CustomEvent).detail?.({ register });
  addEventListener("wallet-standard:register-wallet", onRegister);
  dispatchEvent(new CustomEvent("wallet-standard:app-ready", { detail: { register } }));
  emit();
  const late = setTimeout(emit, 600); // legacy objects can appear a moment after load
  return () => {
    clearTimeout(late);
    removeEventListener("wallet-standard:register-wallet", onRegister);
  };
}

// ---- signing in ----

export function signInText(address: string) {
  const host = location.host;
  const nonce = Array.from(crypto.getRandomValues(new Uint8Array(8)), (b) => b.toString(16).padStart(2, "0")).join("");
  // Plain text on purpose: a first line like "<host> wants you to sign in with your Solana account:"
  // makes Phantom parse it as strict Sign-In With Solana and reject anything not in that exact shape.
  return [
    `Sign in to AsAsked Lab (${host})`,
    "",
    "This is not a transaction and costs nothing. It only keeps your search history in this browser.",
    "",
    `Wallet: ${address}`,
    `Time: ${new Date().toISOString()}`,
    `Code: ${nonce}`,
  ].join("\n");
}

// Ed25519 check of the wallet's signature against its own address. Browsers without Ed25519 in
// WebCrypto skip the check; the session only lives in this browser either way.
async function verify(address: string, message: Uint8Array, signature: Uint8Array) {
  try {
    const key = await crypto.subtle.importKey("raw", b58decode(address) as BufferSource, { name: "Ed25519" }, false, ["verify"]);
    return await crypto.subtle.verify({ name: "Ed25519" }, key, signature as BufferSource, message as BufferSource);
  } catch {
    return true;
  }
}

const b64 = (u: Uint8Array) => btoa(String.fromCharCode(...u));

export async function signIn(w: WalletChoice): Promise<Session> {
  const acct = await w.connect();
  if (await serverOpen()) {
    const c = await post<{ nonce: string; text: string }>("/api/auth/challenge", { address: acct.address });
    const signature = await acct.sign(new TextEncoder().encode(c.text));
    await post("/api/auth/verify", { nonce: c.nonce, signature: b64(signature) });
    const s: Session = { address: acct.address, wallet: w.name, at: new Date().toISOString(), server: true };
    write(SESSION, s);
    changed();
    return s;
  }
  const message = new TextEncoder().encode(signInText(acct.address));
  const signature = await acct.sign(message);
  if (!(await verify(acct.address, message, signature))) throw new Error("The signature did not match this wallet.");
  const s: Session = { address: acct.address, wallet: w.name, at: new Date().toISOString() };
  write(SESSION, s);
  changed();
  return s;
}
