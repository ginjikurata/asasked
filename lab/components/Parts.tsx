// Small server-side building blocks shared by the home, stores and store pages.
import type { Merchant } from "@/lib/merchants";
import { fmtDate, pays, slug } from "@/lib/labels";

export function SectionHead({ title, note, more }: { title: string; note?: string; more?: { href: string; label: string } }) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-x-6 gap-y-1">
      <div className="min-w-0">
        <h2 className="text-[22px] font-semibold tracking-[-0.01em] sm:text-[26px]">{title}</h2>
        {note && <p className="mt-1 text-sm text-muted">{note}</p>}
      </div>
      {more && (
        <a href={more.href} className="link -my-2.5 shrink-0 py-2.5 text-sm">
          {more.label} →
        </a>
      )}
    </div>
  );
}

// One store per line: name and category on the left, how it takes crypto and when we checked on the right.
export function StoreRow({ m, label }: { m: Merchant; label?: string }) {
  return (
    <li className="border-t border-line first:border-t-0">
      <a
        href={`/stores/${slug(m.domain)}`}
        className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-0.5 px-4 py-3 hover:bg-panel sm:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_auto]"
      >
        <span className="min-w-0">
          <span className="block truncate font-medium">{m.name}</span>
          <span className="meta block truncate">{label ?? m.domain}</span>
        </span>
        <span className="hidden truncate text-sm text-muted sm:block">{pays(m)}</span>
        <span className="meta flex items-center gap-1.5 whitespace-nowrap">
          <span className={m.status === "yes" ? "text-pass" : "text-muted"} aria-hidden>
            ●
          </span>
          <span className="sm:hidden">{m.gateway === "unknown" || !m.gateway ? "Crypto" : m.gateway === "own" ? "Own checkout" : m.gateway}</span>
          <span className="hidden sm:inline">{m.checked ? `Checked ${fmtDate(m.checked)}` : "Checked, date not recorded"}</span>
        </span>
      </a>
    </li>
  );
}

export function StoreList({ stores, label }: { stores: Merchant[]; label?: (m: Merchant) => string }) {
  return (
    <ul className="overflow-hidden rounded-xl border border-line">
      {stores.map((m) => (
        <StoreRow key={m.domain} m={m} label={label?.(m)} />
      ))}
    </ul>
  );
}

// A row of pixels whose length shows a count; the pixel motif from the AsAsked mark.
export function PixelBar({ n, max, cells = 20 }: { n: number; max: number; cells?: number }) {
  const on = Math.max(1, Math.round((n / max) * cells));
  return (
    <span aria-hidden className="flex gap-[2px]">
      {Array.from({ length: cells }, (_, i) => (
        <span key={i} className={`size-[7px] ${i < on ? (i === on - 1 ? "bg-signal" : "bg-ink") : "bg-line"}`} />
      ))}
    </span>
  );
}
