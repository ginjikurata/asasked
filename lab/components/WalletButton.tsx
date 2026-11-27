"use client";

import { useEffect, useRef, useState } from "react";
import {
  clearHistory,
  findWallets,
  getHistory,
  getSession,
  onWalletChange,
  serverOpen,
  short,
  signIn,
  signOut,
  syncServer,
  type Past,
  type Session,
  type WalletChoice,
} from "@/lib/wallet";

const ago = (iso: string) => {
  const m = Math.round((Date.now() - Date.parse(iso)) / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} h ago`;
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
};

export function WalletButton() {
  const [session, setSession] = useState<Session | null>(null);
  const [past, setPast] = useState<Past[]>([]);
  const [wallets, setWallets] = useState<WalletChoice[]>([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [accounts, setAccounts] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const sync = () => {
      setSession(getSession());
      setPast(getHistory());
    };
    sync();
    serverOpen().then(setAccounts);
    syncServer();
    const stopWallets = findWallets(setWallets);
    const stopSync = onWalletChange(sync);
    return () => {
      stopWallets();
      stopSync();
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    const close = (e: Event) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !box.current?.contains(e.target as Node)) setOpen(false);
    };
    addEventListener("pointerdown", close);
    addEventListener("keydown", close);
    return () => {
      removeEventListener("pointerdown", close);
      removeEventListener("keydown", close);
    };
  }, [open]);

  async function connect(w: WalletChoice) {
    setBusy(w.name);
    setError("");
    try {
      await signIn(w);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "";
      setError(/reject|denied|cancel/i.test(msg) ? "You cancelled the request in your wallet." : msg || "The wallet did not sign.");
    } finally {
      setBusy("");
    }
  }

  return (
    <div ref={box} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="dialog"
        className={`grid h-8 min-w-8 place-items-center whitespace-nowrap rounded-full border px-2 text-sm sm:px-3 ${
          session ? "border-line bg-panel font-mono text-[12px]" : "border-ink bg-ink text-paper hover:bg-ink/85"
        }`}
      >
        {session ? (
          <>
            {/* Phones: the icon either way, so the header fits; the address is in the panel. */}
            <svg viewBox="0 0 20 20" aria-hidden className="size-4 sm:hidden" fill="none" stroke="currentColor" strokeWidth="1.6">
              <rect x="2.5" y="5" width="15" height="11" rx="2" />
              <path d="M13 10.5h4.5M5 5l8-2.5V5" />
            </svg>
            <span className="sr-only sm:not-sr-only">{short(session.address)}</span>
          </>
        ) : (
          <>
            <svg viewBox="0 0 20 20" aria-hidden className="size-4 sm:hidden" fill="none" stroke="currentColor" strokeWidth="1.6">
              <rect x="2.5" y="5" width="15" height="11" rx="2" />
              <path d="M13 10.5h4.5M5 5l8-2.5V5" />
            </svg>
            <span className="sr-only sm:not-sr-only">Connect wallet</span>
          </>
        )}
      </button>

      {open && (
        <div
          role="dialog"
          aria-label={session ? "Your wallet" : "Connect a wallet"}
          className="absolute right-0 top-10 z-30 whitespace-normal w-[min(20rem,calc(100vw-2*var(--gutter)))] rounded-2xl border border-line bg-paper p-4 text-sm shadow-[0_12px_40px_-12px_rgba(0,0,0,0.25)]"
        >
          {session ? (
            <>
              <p className="meta">Signed in with {session.wallet}</p>
              <p className="mt-0.5 break-all font-mono text-[12px]">{session.address}</p>
              {accounts && (
                <a
                  href="/account"
                  className="mt-3 flex items-center justify-between rounded-xl border border-line px-3 py-2 hover:border-ink"
                >
                  <span>
                    <span className="block font-medium">Your account</span>
                    <span className="block text-[12px] leading-snug text-muted">
                      {session.server ? "Sizes, agent access, saved carts" : "Sign in again to open it"}
                    </span>
                  </span>
                  <span aria-hidden>→</span>
                </a>
              )}
              <h2 className="mt-4 font-medium">Your searches</h2>
              {past.length ? (
                <ul className="mt-1 max-h-64 overflow-y-auto">
                  {past.slice(0, 12).map((h) => (
                    <li key={h.q}>
                      <a href={`/search?q=${encodeURIComponent(h.q)}`} className="-mx-2 flex items-baseline gap-2 rounded-lg px-2 py-1.5 hover:bg-panel">
                        <span className="min-w-0 flex-1 truncate">{h.q}</span>
                        <span className="meta shrink-0">
                          {h.fits !== undefined && <span className="text-pass">{h.fits} fit · </span>}
                          {ago(h.at)}
                        </span>
                      </a>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-muted">Nothing yet. Searches you make while signed in show up here.</p>
              )}
              <p className="mt-3 text-[12px] leading-snug text-muted">Your searches are kept only in this browser and not sent to us.</p>
              <div className="mt-3 flex gap-4 border-t border-line pt-3">
                {past.length > 0 && (
                  <button type="button" onClick={clearHistory} className="link">
                    Clear history
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => {
                    setOpen(false);
                    signOut();
                  }}
                  className="link ml-auto"
                >
                  Disconnect
                </button>
              </div>
            </>
          ) : (
            <>
              <h2 className="font-medium">Sign in with your wallet</h2>
              <p className="mt-1 leading-snug text-muted">
                Your wallet asks you to sign a short text. It is not a transaction: no fee, no money moves.{" "}
                {accounts
                  ? "It opens your account, where you keep your sizes and let your own agent save carts. Your search history stays in this browser."
                  : "We use it only to keep your search history, and that stays in this browser."}
              </p>
              {wallets.length ? (
                <ul className="mt-3 flex flex-col gap-2">
                  {wallets.map((w) => (
                    <li key={w.name}>
                      <button
                        type="button"
                        disabled={Boolean(busy)}
                        onClick={() => connect(w)}
                        className="flex h-10 w-full items-center gap-3 rounded-xl border border-line px-3 text-left hover:border-ink disabled:opacity-50"
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
                <p className="mt-3 rounded-xl bg-panel p-3 leading-snug">
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
            </>
          )}
        </div>
      )}
    </div>
  );
}
