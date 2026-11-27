"use client";

import { useEffect, useMemo, useState } from "react";
import { MERCHANTS } from "@/lib/merchants";
import { toEnglish } from "@/lib/intent";
import { GROUP_LABEL, gatewayName, slug } from "@/lib/labels";
import { StoreRow } from "./Parts";

type Opt = { slug: string; label: string; n: number };

// Store list with search, category chips and a payment-provider filter. ?c=<category-slug> picks a category.
export function Catalog({ cats, sells = {} }: { cats: Opt[]; sells?: Record<string, string> }) {
  const [q, setQ] = useState("");
  const [c, setC] = useState("");
  const [g, setG] = useState("");

  useEffect(() => {
    const p = new URLSearchParams(location.search);
    const v = p.get("c");
    if (v && cats.some((x) => x.slug === v)) setC(v);
    const s = p.get("q");
    if (s) setQ(s);
  }, [cats]);

  const pick = (v: string) => {
    setC(v);
    history.replaceState(null, "", v ? `/stores?c=${v}` : "/stores");
  };

  const gws = useMemo(() => {
    const n = new Map<string, number>();
    for (const m of MERCHANTS) n.set(gatewayName(m.gateway), (n.get(gatewayName(m.gateway)) ?? 0) + 1);
    return [...n].sort((a, b) => b[1] - a[1]);
  }, []);

  const list = useMemo(() => {
    // Russian item words ("обувь") become the English the store data uses ("shoes"), as in product search.
    const words = q.toLowerCase().split(/\s+/).filter(Boolean).flatMap(toEnglish);
    return MERCHANTS.filter((m) => {
      if (c && slug(m.group) !== c) return false;
      if (g && gatewayName(m.gateway) !== g) return false;
      const hay = `${m.name} ${m.domain} ${m.category} ${m.group} ${sells[m.domain] ?? ""}`.toLowerCase();
      return words.every((w) => hay.includes(w));
    }).sort((a, b) => a.name.localeCompare(b.name));
  }, [q, c, g]);

  const chip = (on: boolean) =>
    `flex h-9 shrink-0 items-center gap-1.5 rounded-full border px-3 text-sm ${on ? "border-ink bg-ink text-paper" : "border-line hover:border-ink"}`;

  return (
    <div>
      <div className="flex flex-col gap-3 sm:flex-row">
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Store name, domain or what it sells"
          aria-label="Filter stores"
          className="h-11 min-w-0 flex-1 rounded-xl border border-line bg-panel px-4 text-base outline-none placeholder:text-faint focus:border-ink"
        />
        <label className="flex h-11 items-center gap-2 rounded-xl border border-line bg-panel pl-3 pr-2 text-sm sm:w-64">
          <span className="meta shrink-0">Pays via</span>
          <select value={g} onChange={(e) => setG(e.target.value)} className="h-full min-w-0 flex-1 bg-transparent text-ink outline-none">
            <option value="">Any provider</option>
            {gws.map(([k, n]) => (
              <option key={k} value={k}>
                {k} ({n})
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="-mx-[var(--gutter)] mt-3 flex gap-2 overflow-x-auto px-[var(--gutter)] pb-1 sm:mx-0 sm:flex-wrap sm:px-0">
        <button type="button" onClick={() => pick("")} className={chip(!c)}>
          All <span className="font-mono text-[12px] opacity-60">{MERCHANTS.length}</span>
        </button>
        {cats.map((x) => (
          <button key={x.slug} type="button" onClick={() => pick(x.slug)} className={chip(c === x.slug)} aria-pressed={c === x.slug}>
            {x.label} <span className="font-mono text-[12px] opacity-60">{x.n}</span>
          </button>
        ))}
      </div>

      <p className="meta mt-6 mb-2" aria-live="polite">
        {list.length} {list.length === 1 ? "store" : "stores"}
      </p>
      {list.length ? (
        <ul className="overflow-hidden rounded-xl border border-line">
          {list.map((m) => (
            <StoreRow key={m.domain} m={m} label={`${GROUP_LABEL[m.group] ?? m.group} · ${m.domain}`} />
          ))}
        </ul>
      ) : (
        <p className="rounded-xl border border-line p-6 text-sm text-muted">
          No store matches. Try another word, or{" "}
          <button type="button" className="link text-ink" onClick={() => (setQ(""), setG(""), pick(""))}>
            clear the filters
          </button>
          .
        </p>
      )}
    </div>
  );
}
