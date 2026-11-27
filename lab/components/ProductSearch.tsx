"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { remember } from "@/lib/wallet";
import { cbUrl, giftCardsFor, giftUrl } from "./giftCards";
import { PRODUCT_GRID, ProductCard } from "./ProductCard";
import { checkProduct, hasConditions, isAccessory, parseIntent, relevance, searchText, termMatches, type Intent } from "@/lib/intent";
import type { Data, Product } from "@/lib/products";

const PAGE = 48;

function GiftCards({ q }: { q: string }) {
  const cards = giftCardsFor(q);
  if (!cards.length) return null;
  const link = "flex h-9 items-center gap-1 rounded-lg border border-line bg-paper px-3 text-sm hover:border-ink";
  return (
    <aside aria-label="Gift cards" className="mt-4 rounded-xl border border-line bg-panel p-3">
      <p className="text-sm">
        <span className="font-medium">Or pay a big store with a gift card.</span>
        <span className="text-muted"> These brands don&apos;t take crypto directly; CoinGate and Coinsbee sell their gift cards for crypto.</span>
      </p>
      <ul className="mt-3 flex flex-col gap-2">
        {cards.map((g) => {
          const sellers = [
            { name: "CoinGate", host: "coingate.com", url: giftUrl(g) },
            { name: "Coinsbee", host: "coinsbee.com", url: cbUrl(g) },
          ].filter((x) => x.url);
          return (
            <li key={g.n} className="flex flex-wrap items-center gap-2">
              <span className="basis-full text-sm font-medium sm:min-w-32 sm:basis-auto">{g.n} gift card</span>
              {sellers.map((x) => (
                <a
                  key={x.name}
                  href={x.url!}
                  rel="nofollow noopener noreferrer sponsored"
                  target="_blank"
                  title={`${g.n} gift card on ${x.host}. Check the card's country before paying.`}
                  className={link}
                >
                  {x.name}
                  <span className="text-muted">↗</span>
                </a>
              ))}
            </li>
          );
        })}
      </ul>
      <p className="meta mt-2">Sold by CoinGate or Coinsbee, not us. Cards often work in one country only; check before paying.</p>
    </aside>
  );
}

const SUGGEST = ["black loafers size 42 under $500", "oxford", "loafers", "chelsea boots", "suede", "tent under $2000", "inflatable tent", "stove"];
// Shown under the search box on "All products": the ones that show what a full request can do.
const TRY = new Set(["black loafers size 42 under $500", "tent under $2000", "suede"]);

// Shelves on "All products", built from each store's own category names (Product.k).
type Sub = { id: string; label: string; k: string[] };
type Shelf = { id: string; label: string; domain?: string; k?: string[]; notK?: string[]; subs?: Sub[] };
type Sort = "featured" | "low" | "high";
const BOTTEGA = "bottegasenatore.com";
const RBM = "hot-tent.com";
const SHELVES: Shelf[] = [
  {
    id: "shoes",
    label: "Shoes",
    domain: BOTTEGA,
    notK: ["Accessories"],
    subs: [
      { id: "oxford", label: "Oxford", k: ["Oxford"] },
      { id: "loafers", label: "Loafers", k: ["Mocassin"] },
      { id: "derby", label: "Derby", k: ["Derby"] },
      { id: "monk", label: "Monk straps", k: ["Double Monk Straps"] },
      { id: "boots", label: "Boots", k: ["Ankle boots", "Chelsea Boots"] },
      { id: "sneakers", label: "Sneakers", k: ["Shoes"] },
    ],
  },
  { id: "leather", label: "Leather goods", domain: BOTTEGA, k: ["Accessories"] },
  {
    id: "tents",
    label: "Tents",
    domain: RBM,
    k: ["Inflatable tents", "Tent", "Bundle", "Bundle-hot-tent"],
    subs: [
      { id: "inflatable", label: "Inflatable", k: ["Inflatable tents"] },
      { id: "hot-tents", label: "Hot tents", k: ["Tent"] },
      { id: "bundles", label: "Bundles", k: ["Bundle", "Bundle-hot-tent"] },
    ],
  },
  { id: "floors", label: "Floors & canopies", domain: RBM, k: ["Floor", "Inflatable Canopy"] },
  { id: "stoves", label: "Stoves", domain: RBM, k: ["Stove", "Heater"] },
  { id: "gear", label: "Camping gear", domain: RBM, k: ["Accessories"] },
];

function resolve(id: string): { shelf?: Shelf; sub?: Sub } {
  for (const shelf of SHELVES) {
    if (shelf.id === id) return { shelf };
    const sub = shelf.subs?.find((s) => s.id === id);
    if (sub) return { shelf, sub };
  }
  return {};
}

const shelfFrom = (c: string | null) => (c && resolve(c).shelf ? c : "");

function onShelf(p: Product, domain: string, shelf?: Shelf, sub?: Sub) {
  if (!shelf) return true;
  return (
    (!shelf.domain || shelf.domain === domain) &&
    (!shelf.k || shelf.k.includes(p.k)) &&
    (!shelf.notK || !shelf.notK.includes(p.k)) &&
    (!sub || sub.k.includes(p.k))
  );
}

function Note() {
  return (
    <p className="meta mt-8 max-w-[70ch]">
      “Buy” opens the store&apos;s own checkout with the item already in the cart; you pay the store, not us.
      Prices and stock come from each store&apos;s feed and may have changed; the store&apos;s own page is
      always right. Crypto payments can&apos;t be reversed, so check the domain and amount on the store&apos;s
      checkout.
    </p>
  );
}

const pill = (on: boolean, small = false) =>
  `inline-flex shrink-0 items-center gap-1.5 rounded-full border text-sm ${small ? "h-8 px-3" : "h-9 px-3.5"} ${
    on ? "border-ink bg-ink text-paper" : "border-line text-ink hover:border-ink"
  }`;

function Count({ n, on }: { n: number; on: boolean }) {
  return <span className={`text-[12px] tabular-nums ${on ? "text-paper/70" : "text-faint"}`}>{n}</span>;
}

// Words people search for that the store's own category names spell differently.
function SearchBox({ value, onChange, onSubmit, big }: { value: string; onChange: (v: string) => void; onSubmit: () => void; big: boolean }) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <form
      role="search"
      onSubmit={(e) => {
        e.preventDefault();
        ref.current?.blur();
        onSubmit();
      }}
      className={`flex w-full items-center gap-2 rounded-full border border-line bg-panel pl-5 pr-2 focus-within:border-ink ${big ? "h-16" : "h-12"}`}
    >
      <input
        ref={ref}
        type="search"
        aria-label="Search products"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="e.g. black loafers, size 42, under $500"
        autoFocus={big}
        enterKeyHint="search"
        className={`h-full min-w-0 flex-1 bg-transparent text-ink outline-none placeholder:text-faint ${big ? "text-lg" : "text-base"}`}
      />
      <button
        type="submit"
        aria-label="Search"
        disabled={!value.trim()}
        className={`grid shrink-0 place-items-center rounded-full bg-signal text-white disabled:opacity-40 ${big ? "size-11" : "size-9"}`}
      >
        <svg viewBox="0 0 16 16" className="size-4" aria-hidden fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M3 8h10M9 4l4 4-4 4" />
        </svg>
      </button>
    </form>
  );
}

function Chip({ k, v }: { k: string; v: string }) {
  return (
    <span className="inline-flex h-7 items-center gap-1 rounded-full border border-line bg-paper px-2.5 text-sm">
      <span className="text-muted">{k}</span>
      <span className="font-medium">{v}</span>
    </span>
  );
}

// What we understood from the request, and how many results meet all of it.
function Asked({ intent, total, fitting }: { intent: Intent; total: number; fitting: number }) {
  return (
    <aside aria-label="Your request" className="mt-4 rounded-xl border border-line bg-panel p-3">
      <p className="font-mono text-[11px] uppercase tracking-wider text-faint">We read your request as</p>
      <div className="mt-2 flex flex-wrap gap-2">
        <Chip k="Item" v={intent.terms.length ? intent.terms.join(" ") : "anything"} />
        {intent.size && <Chip k="Size" v={intent.size} />}
        {intent.color && <Chip k="Color" v={intent.color} />}
        {intent.option && <Chip k="Condition" v={intent.option} />}
        {intent.budget !== undefined && <Chip k="Up to" v={`$${intent.budget.toLocaleString("en-US")}`} />}
        {intent.crypto && <Chip k="Pay" v="crypto" />}
      </div>
      {hasConditions(intent) && (
        <p className="mt-2 text-sm" aria-live="polite">
          <span className="font-semibold text-pass">{fitting} fit everything</span>
          <span className="text-muted">{total - fitting ? ` · ${total - fitting} close; the card says what differs` : ""}</span>
        </p>
      )}
      {intent.crypto && <p className="meta mt-1">We found a crypto option at every store here; check the checkout before you pay.</p>}
    </aside>
  );
}

export function ProductSearch() {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState(false);
  const [draft, setDraft] = useState("");
  const [q, setQ] = useState("");
  const [store, setStore] = useState("");
  const [inStock, setInStock] = useState(true);
  const [limit, setLimit] = useState(PAGE);
  const [cat, setCat] = useState("");
  const [sort, setSort] = useState<Sort>("featured");
  const [filtersOpen, setFiltersOpen] = useState(false);

  useEffect(() => {
    fetch("/products.json")
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setData)
      .catch(() => setError(true));
    const fromUrl = () => {
      const params = new URLSearchParams(location.search);
      const v = params.get("q") ?? "";
      setDraft(v);
      setQ(v);
      setCat(shelfFrom(params.get("c")));
      const so = params.get("sort");
      setSort(so === "low" || so === "high" ? so : "featured");
      setInStock(params.get("stock") !== "all");
    };
    fromUrl();
    addEventListener("popstate", fromUrl);
    return () => removeEventListener("popstate", fromUrl);
  }, []);

  // Shelf, sort and an unticked "In stock only" live in the address (?c=shoes&stock=all),
  // so a shared link, reload or Back keeps them.
  const toUrl = (u: URLSearchParams, stock: boolean) => {
    if (stock) u.delete("stock");
    else u.set("stock", "all");
    const t = u.toString();
    return t ? `/search?${t}` : "/search";
  };
  function listUrl(c: string, so: Sort) {
    const u = new URLSearchParams();
    if (c) u.set("c", c);
    if (so !== "featured") u.set("sort", so);
    return toUrl(u, inStock);
  }
  function pickStock(on: boolean) {
    setInStock(on);
    history.replaceState(null, "", toUrl(new URLSearchParams(location.search), on));
  }
  function pick(id: string) {
    setCat(id);
    history.replaceState(null, "", listUrl(id, sort));
  }
  function pickSort(so: Sort) {
    setSort(so);
    history.replaceState(null, "", listUrl(cat, so));
  }

  function search(value: string) {
    const v = value.trim();
    setDraft(v);
    if (v === q) return;
    setQ(v);
    setStore("");
    history.pushState(null, "", toUrl(new URLSearchParams(v ? { q: v } : {}), inStock));
    scrollTo(0, 0);
  }

  const index = useMemo(
    () => data?.products.map((p) => searchText(p, data.stores[p.s])) ?? [],
    [data],
  );

  const match = (words: string[], n: number) => words.every((w) => termMatches(w, index[n]));
  const intent = useMemo(() => parseIntent(q), [q]);
  const guard = hasConditions(intent);

  // Products whose item words match; with conditions, each also gets a guard check, fits first.
  const shown = useMemo(() => {
    if (!data || (!intent.terms.length && !guard)) return [];
    const rows = data.products
      .map((p, n) => ({ p, n }))
      .filter(({ p, n }) => (!inStock || p.a) && (!store || data.stores[p.s].domain === store) && match(intent.terms, n))
      .map(({ p }) => ({ p, check: guard ? checkProduct(p, data.stores[p.s], intent) : undefined }));
    // Fits first, then the item itself before things that only mention it ("stove" finds stoves before
    // tents "with Stove Jack"), accessories last.
    rows.sort(
      (a, b) =>
        (guard ? a.check!.bad.length - b.check!.bad.length : 0) ||
        relevance(a.p, intent.terms) - relevance(b.p, intent.terms) ||
        Number(isAccessory(a.p)) - Number(isAccessory(b.p)),
    );
    return rows;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, index, intent, store, inStock]);
  const fitting = shown.filter((r) => r.check?.fits).length;

  const suggestions = useMemo(
    () => (data ? SUGGEST.filter((s) => data.products.some((p, n) => p.a && match(parseIntent(s).terms, n))) : []),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [data, index],
  );

  // "All products": everything on the chosen shelf. Featured puts items with photos first, then lets the stores take turns.
  const all = useMemo(() => {
    if (!data) return [];
    const { shelf, sub } = resolve(cat);
    const rows = data.products.filter(
      (p) => (!inStock || p.a) && (!store || data.stores[p.s].domain === store) && onShelf(p, data.stores[p.s].domain, shelf, sub),
    );
    if (sort === "low") return [...rows].sort((a, b) => a.p - b.p);
    if (sort === "high") return [...rows].sort((a, b) => b.p - a.p);
    const turn = new Map<number, number>();
    const rest = rows
      .filter((p) => !p.m)
      .map((p) => {
        const r = turn.get(p.s) ?? 0;
        turn.set(p.s, r + 1);
        return { p, r };
      })
      .sort((a, b) => a.r - b.r || a.p.s - b.p.s);
    return [...rows.filter((p) => p.m), ...rest.map((x) => x.p)];
  }, [data, cat, store, inStock, sort]);

  // Items per shelf (for the pills) given the store and stock filters; "" is all of them.
  const shelfCounts = useMemo(() => {
    const m = new Map<string, number>();
    const add = (id: string) => m.set(id, (m.get(id) ?? 0) + 1);
    data?.products.forEach((p) => {
      const domain = data.stores[p.s].domain;
      if ((inStock && !p.a) || (store && domain !== store)) return;
      add("");
      for (const shelf of SHELVES) {
        if (!onShelf(p, domain, shelf)) continue;
        add(shelf.id);
        for (const sub of shelf.subs ?? []) if (onShelf(p, domain, shelf, sub)) add(sub.id);
      }
    });
    return m;
  }, [data, store, inStock]);

  // Items per store on the chosen shelf (for the store filter).
  const storeCounts = useMemo(() => {
    const m = new Map<number, number>();
    const { shelf, sub } = resolve(cat);
    data?.products.forEach((p) => {
      if ((!inStock || p.a) && onShelf(p, data.stores[p.s].domain, shelf, sub)) m.set(p.s, (m.get(p.s) ?? 0) + 1);
    });
    return m;
  }, [data, cat, inStock]);

  useEffect(() => setLimit(PAGE), [q, store, inStock, cat, sort]);

  // Signed in with a wallet: keep this search in the browser's own history list.
  useEffect(() => {
    if (data && q) remember(q, guard ? fitting : undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, q]);

  if (!q) {
    const { shelf: open, sub: openSub } = resolve(cat);
    const tries = suggestions.filter((s) => TRY.has(s));
    const filters = (store ? 1 : 0) + (inStock ? 0 : 1);
    return (
      <section aria-label="All products" className="pt-8 sm:pt-12">
        <div className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between md:gap-10">
          <div className="min-w-0">
            <h1 className="text-[36px] font-semibold leading-[1.02] tracking-[-0.03em] sm:text-[56px]">All products</h1>
            <p className="mt-3 max-w-[46ch] text-muted">
              {data ? `${data.products.length} items (${data.products.filter((p) => p.a).length} in stock) from ${data.stores.length} stores` : "Items from stores"}{" "}
              that take crypto.
            </p>
          </div>
          <div className="w-full md:max-w-sm">
            <SearchBox value={draft} onChange={setDraft} onSubmit={() => search(draft)} big={false} />
            <p className="mt-2 min-h-5 text-[13px] text-muted">
              {tries.length > 0 && "Or ask in full: "}
              {tries.map((s, i) => (
                <span key={s}>
                  {i > 0 && ", "}
                  <button
                    type="button"
                    onClick={() => search(s)}
                    className="underline decoration-line underline-offset-2 hover:text-ink hover:decoration-ink"
                  >
                    {s}
                  </button>
                </span>
              ))}
            </p>
          </div>
        </div>

        <nav
          aria-label="Categories"
          className="-mx-[var(--gutter)] mt-8 overflow-x-auto px-[var(--gutter)] [scrollbar-width:none] sm:mt-10 [&::-webkit-scrollbar]:hidden"
        >
          <ul className="flex gap-2 whitespace-nowrap md:flex-wrap">
            <li>
              <button type="button" aria-pressed={!cat} onClick={() => pick("")} className={pill(!cat)}>
                All {data ? <Count n={shelfCounts.get("") ?? 0} on={!cat} /> : <span className="text-faint">…</span>}
              </button>
            </li>
            {SHELVES.map((s) => {
              const on = open?.id === s.id;
              const n = shelfCounts.get(s.id) ?? 0;
              if (!n && !on) return null;
              return (
                <li key={s.id}>
                  <button type="button" aria-pressed={on} onClick={() => pick(s.id)} className={pill(on)}>
                    {s.label} <Count n={n} on={on} />
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>

        {open?.subs && (
          <ul aria-label={`Kinds of ${open.label.toLowerCase()}`} className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-sm">
            {[{ id: open.id, label: `All ${open.label.toLowerCase()}` }, ...open.subs].map((s) => {
              const on = s.id === open.id ? !openSub : openSub?.id === s.id;
              const n = shelfCounts.get(s.id) ?? 0;
              if (!n && !on) return null;
              return (
                <li key={s.id}>
                  <button
                    type="button"
                    aria-pressed={on}
                    onClick={() => pick(s.id)}
                    className={on ? "font-medium text-ink underline decoration-2 underline-offset-[6px]" : "text-muted hover:text-ink"}
                  >
                    {s.label} <span className="text-[12px] tabular-nums text-faint">{n}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}

        <div className="mt-6 flex items-center justify-between gap-3 border-t border-line pt-4">
          <p className="text-sm" aria-live="polite">
            <span className="font-semibold">{data ? all.length : "…"}</span>
            <span className="text-muted"> {inStock ? "in stock" : "items"}</span>
          </p>
          <div className="flex items-center gap-2">
            <select
              aria-label="Sort"
              value={sort}
              onChange={(e) => pickSort(e.target.value as Sort)}
              className="h-9 rounded-full border border-line bg-paper px-3 text-sm text-ink hover:border-ink"
            >
              <option value="featured">Featured</option>
              <option value="low">Lowest price</option>
              <option value="high">Highest price</option>
            </select>
            <button
              type="button"
              aria-expanded={filtersOpen}
              aria-controls="filters"
              onClick={() => setFiltersOpen(!filtersOpen)}
              className="inline-flex h-9 items-center gap-2 rounded-full border border-line px-4 text-sm hover:border-ink"
            >
              Filters{filters ? ` (${filters})` : ""}
              <span aria-hidden className="w-2 font-mono">
                {filtersOpen ? "–" : "+"}
              </span>
            </button>
          </div>
        </div>

        <div id="filters" hidden={!filtersOpen} className="mt-4 rounded-xl border border-line bg-panel p-4">
          <p className="font-mono text-[11px] uppercase tracking-wider text-faint">Store</p>
          <ul className="mt-2 flex flex-wrap gap-2">
            <li>
              <button type="button" aria-pressed={!store} onClick={() => setStore("")} className={pill(!store, true)}>
                All stores
              </button>
            </li>
            {data?.stores.map((s, n) => {
              const on = store === s.domain;
              const c = storeCounts.get(n) ?? 0;
              if (!c && !on) return null;
              return (
                <li key={s.domain}>
                  <button type="button" aria-pressed={on} onClick={() => setStore(on ? "" : s.domain)} className={pill(on, true)}>
                    {s.name} <Count n={c} on={on} />
                  </button>
                </li>
              );
            })}
          </ul>
          <label className="mt-2 flex items-center gap-2 py-2 text-sm">
            <input type="checkbox" checked={inStock} onChange={(e) => pickStock(e.target.checked)} />
            In stock only
          </label>
        </div>

        {error ? (
          <p className="mt-10 text-center text-muted">Could not load the product list. Try reloading the page.</p>
        ) : !data ? (
          <p className="meta mt-10 text-center">Loading products…</p>
        ) : all.length ? (
          <>
            <ul className={`mt-6 ${PRODUCT_GRID}`}>
              {all.slice(0, limit).map((p) => (
                <ProductCard key={p.u} p={p} store={data.stores[p.s]} />
              ))}
            </ul>
            {all.length > limit && (
              <button
                type="button"
                onClick={() => setLimit(limit + PAGE)}
                className="mt-10 h-11 w-full rounded-full border border-line text-sm hover:border-ink"
              >
                Show more ({all.length - limit} left)
              </button>
            )}
          </>
        ) : (
          <p className="mt-10 text-center text-muted">
            Nothing here{inStock ? " in stock right now. Untick “In stock only” under Filters to see sold-out items" : ""}.
          </p>
        )}
        <Note />
      </section>
    );
  }

  const counts = new Map<number, number>();
  if (data) {
    data.products.forEach((p, n) => {
      if ((!inStock || p.a) && match(intent.terms, n)) counts.set(p.s, (counts.get(p.s) ?? 0) + 1);
    });
  }

  return (
    <section aria-label="Results" className="pt-6">
      <h1 className="sr-only">Search results for {q}</h1>
      <div className="mx-auto max-w-2xl">
        <SearchBox value={draft} onChange={setDraft} onSubmit={() => search(draft)} big={false} />
      </div>

      {error ? (
        <p className="mt-8 text-center text-muted">Could not load the product list. Try reloading the page.</p>
      ) : !data ? (
        <p className="meta mt-8 text-center">Loading products…</p>
      ) : (
        <>
          <div className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-3">
            <p className="text-sm" aria-live="polite">
              <span className="font-semibold">{shown.length}</span>
              <span className="text-muted"> results for “{q}”</span>
            </p>
            <select
              aria-label="Store"
              value={store}
              onChange={(e) => setStore(e.target.value)}
              className="h-9 min-w-0 max-w-full rounded-lg border border-line bg-paper px-2 text-sm text-ink"
            >
              <option value="">All stores</option>
              {data.stores.map((s, n) =>
                counts.get(n) || s.domain === store ? (
                  <option key={s.domain} value={s.domain}>
                    {s.name} ({counts.get(n) ?? 0})
                  </option>
                ) : null,
              )}
            </select>
            <label className="-my-2 flex items-center gap-2 py-2 text-sm">
              <input type="checkbox" checked={inStock} onChange={(e) => pickStock(e.target.checked)} />
              In stock only
            </label>
          </div>

          {(guard || intent.crypto) && <Asked intent={intent} total={shown.length} fitting={fitting} />}

          <GiftCards q={intent.terms.join(" ")} />

          {shown.length ? (
            <>
              <ul className={`mt-4 ${PRODUCT_GRID}`}>
                {shown.slice(0, limit).map(({ p, check }) => (
                  <ProductCard key={p.u} p={p} store={data.stores[p.s]} check={check} size={intent.size ?? intent.option} />
                ))}
              </ul>
              {shown.length > limit && (
                <button
                  type="button"
                  onClick={() => setLimit(limit + PAGE)}
                  className="mt-6 h-10 w-full rounded-xl border border-line text-sm hover:bg-panel"
                >
                  Show more ({shown.length - limit} left)
                </button>
              )}
            </>
          ) : (
            <div className="mt-10 text-center">
              <p className="text-muted">Nothing found. Try a shorter query{inStock ? " or untick “In stock only”" : ""}.</p>
              <div className="mt-4 flex flex-wrap justify-center gap-2">
                {suggestions.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => search(s)}
                    className="h-8 rounded-full border border-line px-3 text-sm text-muted hover:border-ink hover:text-ink"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
          <Note />
        </>
      )}
    </section>
  );
}
