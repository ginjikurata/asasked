"use client";
import { useState } from "react";
import type { Check } from "@/lib/intent";
import { money, price, shortTitle, variesInPrice, type Product, type Store } from "@/lib/products";

// Product grid: two columns on phones, three from md; tight gaps across, more air between rows.
export const PRODUCT_GRID = "grid grid-cols-2 gap-x-3 gap-y-9 md:grid-cols-3";

// Stores whose photo-less items are trading cards: those get a drawn card outline.
const CARD_STORES = new Set(["satoshitcg.com"]);

// Options still in stock (stock unknown counts as in stock).
const inStock = (p: Product) => (p.v ?? []).filter(([, , , s]) => s !== false);
const isSize = (l: string) => /^[0-9.]+$/.test(l);

function Buy({ p, store, size }: { p: Product; store: Store; size?: string }) {
  // Preselect the size the person asked for, or the only option left. When the asked size is not
  // in stock, nothing is preselected: a 45 must not slip into the cart of someone who asked for 42.
  const [pick, setPick] = useState(() => {
    const left = inStock(p);
    if (size) return String(left.find(([, l]) => l.toLowerCase() === size.toLowerCase())?.[0] ?? "");
    return String(left.length === 1 ? left[0][0] : "");
  });
  if (!store.cart || !p.i || !p.a) return null;
  if (store.down)
    return (
      <p className="mt-auto pt-3 text-[13px] leading-snug text-muted">
        Store site not responding (checked {fmtDay(store.down)}). Buying is paused.
      </p>
    );
  const many = (p.v?.length ?? 0) > 1;
  const id = p.v ? (many ? pick : String(p.v[0][0])) : String(p.i);
  const btn =
    "grid h-8 shrink-0 place-items-center rounded-full border border-ink px-4 text-[13px] font-medium text-ink hover:bg-ink hover:text-paper";
  const chosen = p.v?.find(([vid]) => String(vid) === id);
  const varies = variesInPrice(p);
  // Read by the AsAsked Lab browser helper (if installed) to check the store's cart against this choice.
  const order = JSON.stringify({ store: store.domain, title: p.t, size: chosen?.[1] ?? "", price: typeof chosen?.[2] === "number" ? chosen[2] : p.p, currency: p.c, id });
  return (
    <div className="mt-auto flex items-center gap-2 pt-3">
      {many && (
        <select
          aria-label={`${CARD_STORES.has(store.domain) ? "Condition" : "Size or option"} for ${p.t}`}
          value={pick}
          onChange={(e) => setPick(e.target.value)}
          className="h-8 min-w-0 flex-1 rounded-full border border-line bg-panel px-2.5 text-[13px] text-ink"
        >
          <option value="">{p.v!.every(([, l]) => isSize(l)) ? "Size" : CARD_STORES.has(store.domain) ? "Condition" : "Option"}</option>
          {p.v!.map(([vid, label, cost, inStock]) => (
            <option key={vid} value={vid} disabled={inStock === false}>
              {label}
              {varies && typeof cost === "number" ? ` · ${money(cost, p.c)}` : ""}
              {inStock === false ? " · sold out" : ""}
            </option>
          ))}
        </select>
      )}
      {id ? (
        <a
          href={store.cart + id}
          data-asasked-order={order}
          rel="nofollow noopener noreferrer"
          target="_blank"
          aria-label={`Buy ${shortTitle(p.t)} on ${store.domain}`}
          title={`Opens ${store.domain} checkout with this item in the cart. Pay with ${store.via}.`}
          className={`${btn} ${many ? "" : "flex-1"}`}
        >
          Buy
        </a>
      ) : (
        <span className={`${btn} pointer-events-none opacity-35`} title="Choose a size first">
          Buy
        </span>
      )}
    </div>
  );
}

const fmtDay = (d: string) => new Date(`${d}T12:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

// No photo: trading cards get a drawn card back (no text: the title is right under it), anything else a plain type tile.
function NoPhoto({ p, store }: { p: Product; store: Store }) {
  if (CARD_STORES.has(store.domain)) {
    return (
      <div aria-hidden className="grid h-full place-items-center">
        <div className="grid aspect-[5/7] h-[70%] place-items-center rounded-lg border-[5px] border-paper bg-[#e4ddd0] shadow-[0_1px_3px_rgba(0,0,0,0.12)] ring-1 ring-line">
          <svg viewBox="0 0 24 24" className="size-8 text-faint" fill="none" stroke="currentColor" strokeWidth="1.5">
            <circle cx="12" cy="12" r="8" />
            <path d="M4 12h5m6 0h5" />
            <circle cx="12" cy="12" r="2.5" />
          </svg>
        </div>
      </div>
    );
  }
  return (
    <div aria-hidden className="flex h-full flex-col items-center justify-center gap-2 px-[12%] text-center">
      {p.k && <span className="font-mono text-[10px] uppercase tracking-wider text-faint sm:text-[11px]">{p.k.replace(/-/g, " ")}</span>}
      <span className="line-clamp-3 text-[14px] font-medium leading-snug text-ink/75 sm:text-[17px]">{shortTitle(p.t)}</span>
      <span className="meta text-[11px]">Photo on the store&apos;s page</span>
    </div>
  );
}

function Badge({ tone, children }: { tone: "pass" | "warn" | "plain"; children: React.ReactNode }) {
  const dot = tone === "pass" ? "bg-pass" : tone === "warn" ? "bg-[#c98a12]" : "bg-faint";
  return (
    <span className="inline-flex h-6 items-center gap-1.5 rounded-full bg-panel px-2 text-[12px] font-medium text-ink ring-1 ring-line">
      <span aria-hidden className={`size-1.5 rounded-full ${dot}`} />
      {children}
    </span>
  );
}

// Second grey line: sizes still in stock, or the short rest of the title ("Holofoil").
function detail(p: Product) {
  const left = inStock(p);
  if (p.a && p.v && p.v.length > 1 && left.length === 1) return `Only ${isSize(left[0][1]) ? "size " : ""}${left[0][1]} left`;
  const sizes = left.filter(([, l]) => isSize(l)).length;
  if (sizes > 1) return `${sizes} sizes in stock`;
  const short = shortTitle(p.t);
  const rest = p.t.slice(short.length).replace(/^\s*[–—-]\s*|^,\s*/, "");
  // "Normal" is the card's print (not holo): it means nothing to a shopper.
  return rest && rest.length <= 28 && !/^normal$/i.test(rest) ? rest : "";
}

export function ProductCard({ p, store, showStore = true, check, size }: { p: Product; store: Store; showStore?: boolean; check?: Check; size?: string }) {
  const sub = [showStore && store.name, detail(p)].filter(Boolean).join(" · ");
  return (
    <li className="group flex min-w-0 flex-col">
      <a href={p.u} rel="nofollow noopener noreferrer" target="_blank" title={p.t} className="block">
        <div className="relative aspect-square overflow-hidden rounded-xl bg-[#f1ece3]">
          {p.m ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={p.m}
              alt=""
              loading="lazy"
              className="size-full object-contain p-[9%] mix-blend-multiply transition-transform duration-300 group-hover:scale-[1.04]"
            />
          ) : (
            <NoPhoto p={p} store={store} />
          )}
          {(check || !p.a) && (
            <div className="absolute left-2.5 top-2.5 flex flex-wrap gap-1.5">
              {!p.a && <Badge tone="plain">Sold out</Badge>}
              {check && (check.fits ? <Badge tone="pass">Fits</Badge> : <Badge tone="warn">Differs</Badge>)}
            </div>
          )}
        </div>
        {/* Phones: title on up to two lines, price under it. From sm: one line, "title — price". */}
        <div className="mt-2.5 text-[14px] leading-snug sm:flex sm:items-baseline sm:gap-1.5 sm:text-[15px]">
          <h3 className="line-clamp-2 min-w-0 font-medium group-hover:underline sm:line-clamp-1">{shortTitle(p.t)}</h3>
          <span aria-hidden className="hidden text-faint sm:inline">
            —
          </span>
          <span className="mt-0.5 block whitespace-nowrap sm:mt-0 sm:shrink-0">{price(p)}</span>
        </div>
        {sub && <p className="mt-0.5 line-clamp-2 text-[13px] leading-snug text-muted">{sub}</p>}
      </a>
      {check && (check.fits ? check.good.length > 0 : check.bad.length > 0) && (
        <p className={`mt-1 line-clamp-2 text-[13px] leading-snug ${check.fits ? "text-pass" : "text-[#9a6a0c]"}`}>
          {check.fits ? check.good.join(" · ") : check.bad.join(" · ")}
        </p>
      )}
      <Buy p={p} store={store} size={check && size} />
    </li>
  );
}
