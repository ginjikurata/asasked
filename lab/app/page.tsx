import { HomeSearch } from "@/components/HomeSearch";
import { SectionHead } from "@/components/Parts";
import { ProductCard } from "@/components/ProductCard";
import { GIFT_CARDS } from "@/components/giftCards";
import { fmtDate, groups, loadProducts, slug } from "@/lib/catalog";
import { MERCHANTS, lastChecked } from "@/lib/merchants";
import { canBuy, type Data, type Product } from "@/lib/products";

// Soft blurred pixels behind the first screen: the AsAsked pixel motif, out of focus.
const GLOW = [
  { c: "#f4b89a", x: "6%", y: "18%", s: 120 },
  { c: "#e3cff0", x: "14%", y: "52%", s: 90 },
  { c: "#f0d6b0", x: "80%", y: "10%", s: 140 },
  { c: "#f4b89a", x: "88%", y: "46%", s: 80 },
  { c: "#cfe0f0", x: "70%", y: "68%", s: 100 },
  { c: "#f0d6b0", x: "26%", y: "78%", s: 70 },
];

const CHIPS = [
  { label: "Loafers", href: "/search?q=loafers", icon: "M3 11h8l2-3h0a1 1 0 0 1 1 1v3H3z" },
  { label: "Tents", href: "/search?q=tent", icon: "M1.5 13.5L8 2.5l6.5 11zM8 13.5l-2-3.5h4z" },
  { label: "Gold and silver", href: "/stores?c=precious-metals", icon: "M2.5 12.5l2-4h7l2 4zM5 8.5l1.5-3h3l1.5 3" },
  { label: "Flights", href: "/stores?c=travel", icon: "M2 9l12-5-4 9-2-3z" },
  { label: "VPN and software", href: "/stores?c=software-and-web", icon: "M8 2l5 2v4c0 3-2.5 5-5 6-2.5-1-5-3-5-6V4z" },
  { label: "Gift cards", href: "/gift-cards", icon: "M2.5 6h11v7.5h-11zM8 6v7.5M2.5 6h11V4h-11z" },
];

// Up to n in-stock products of one store, one per product type first so a shelf isn't eight black oxfords.
function shelf(data: Data, domain: string, n: number, order: (a: Product, b: Product) => number = () => 0) {
  const s = data.stores.findIndex((x) => x.domain === domain);
  const all = data.products.filter((p) => p.s === s && p.a && p.i).sort(order);
  const seen = new Set<string>();
  const first = all.filter((p) => (seen.has(p.k) ? false : (seen.add(p.k), true)));
  const picked = [...first, ...all.filter((p) => !first.includes(p))].slice(0, n);
  return { store: data.stores[s], picked, total: data.products.filter((p) => p.s === s).length };
}

function Shelf({ data, domain, title, note, order }: { data: Data; domain: string; title: string; note: string; order?: (a: Product, b: Product) => number }) {
  const { store, picked, total } = shelf(data, domain, 4, order);
  if (!store || store.down || !picked.length) return null;
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h3 className="text-[17px] font-semibold">
          {title} <span className="font-normal text-muted">· {store.name}</span>
        </h3>
        <p className="meta">
          {note} ·{" "}
          <a href={`/stores/${slug(domain)}`} className="link inline-block py-2 text-ink">
            all {total}
          </a>
        </p>
      </div>
      <ul className="grid grid-cols-2 gap-x-3 gap-y-8 md:grid-cols-4">
        {picked.map((p) => (
          <ProductCard key={p.u} p={p} store={store} showStore={false} />
        ))}
      </ul>
    </div>
  );
}

export default function Home() {
  const data = loadProducts();
  const gs = groups();
  const checked = fmtDate(lastChecked());
  // Only stores whose cart link works today: a store whose site is down has its Buy buttons hidden.
  const withBuy = data.stores.filter(canBuy).length;
  // Sold-out products show "Sold out" instead of Buy, so they are not counted.
  const buyable = data.products.filter((p) => canBuy(data.stores[p.s]) && p.i && p.a).length;

  const stats = [
    { n: String(MERCHANTS.length), label: "stores checked on their own site" },
    { n: String(buyable), label: "products with a Buy button" },
    { n: "0", label: "ads, trackers or passwords" },
    { n: "$0", label: "of your money held by us" },
  ];

  const steps = [
    ["Find", "Search products or pick a store from the list. Every store was checked on its own site; each shows when we last saw crypto there."],
    ["Pay the store", "“Buy” or “Visit” takes you to the store's own site. You pay them in crypto; nothing goes through us."],
    ["Check the checkout", "Crypto payments can't be reversed. Check the domain and the amount on the store's checkout before paying."],
  ];

  return (
    <main>
      {/* ── First screen ─────────────────────────────── */}
      <section className="relative overflow-hidden">
        <div aria-hidden className="pointer-events-none absolute inset-0">
          {GLOW.map((g, i) => (
            <span
              key={i}
              className="absolute rounded-[18%] blur-3xl"
              style={{ left: g.x, top: g.y, width: g.s, height: g.s, background: g.c, opacity: 0.85 }}
            />
          ))}
        </div>
        <div className="wide relative flex flex-col items-center pb-16 pt-14 text-center sm:pb-20 sm:pt-24">
          <p className="inline-flex items-center gap-2 rounded-full border border-line bg-panel px-3 py-1.5 text-[13px] text-muted">
            <span className="size-2 rounded-full bg-pass" aria-hidden />
            {MERCHANTS.length} stores · last checked {checked}
          </p>
          <h1 className="mt-6 max-w-[16ch] text-balance text-[40px] font-semibold leading-[1.03] tracking-[-0.035em] sm:text-[64px]">
            Shops that take crypto, checked one by one
          </h1>
          <p className="mt-5 max-w-[46ch] text-balance text-[17px] text-muted sm:text-lg">
            Search products, stores and gift cards. You pay the store directly on its own checkout; we never hold your
            money.
          </p>
          <div className="mt-8 w-full max-w-xl">
            <HomeSearch placeholder="Try “loafers” or “tent”" />
          </div>
          <ul className="mt-5 flex max-w-2xl flex-wrap justify-center gap-2">
            {CHIPS.map((c) => (
              <li key={c.label}>
                <a
                  href={c.href}
                  className="flex h-9 items-center gap-2 rounded-full border border-line bg-panel px-3.5 text-sm hover:border-ink"
                >
                  <svg viewBox="0 0 16 16" className="size-4 text-muted" aria-hidden fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round">
                    <path d={c.icon} />
                  </svg>
                  {c.label}
                </a>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section aria-label="In numbers" className="wide">
        <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {stats.map((s) => (
            <div key={s.label} className="flex flex-col-reverse rounded-2xl bg-panel p-5">
              <dt className="mt-1 text-sm text-muted">{s.label}</dt>
              <dd className="text-[30px] font-semibold tracking-tight sm:text-[36px]">{s.n}</dd>
            </div>
          ))}
        </dl>
      </section>

      {/* ── Buy here ─────────────────────────────────── */}
      <section className="wide mt-20 sm:mt-28">
        <SectionHead
          title="Buy in one click"
          note={`${withBuy} ${withBuy === 1 ? "store" : "stores"} where “Buy” opens ${withBuy === 1 ? "its" : "their"} checkout with the item already in the cart.`}
          more={{ href: "/search", label: "Search all products" }}
        />
        <div className="flex flex-col gap-10">
          <Shelf data={data} domain="bottegasenatore.com" title="Handmade Italian shoes" note="pay via BitPay" />
        </div>
      </section>

      {/* ── Categories ───────────────────────────────── */}
      <section className="wide mt-20 sm:mt-28">
        <SectionHead title="Browse by category" more={{ href: "/stores", label: `All ${MERCHANTS.length} stores` }} />
        <ul className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
          {gs.map((g) => (
            <li key={g.key}>
              <a
                href={g.key === "gift cards" ? "/gift-cards" : `/stores?c=${g.slug}`}
                className="flex h-full flex-col rounded-2xl border border-transparent bg-panel p-4 hover:border-line"
              >
                <span className="flex items-baseline justify-between gap-2">
                  <span className="font-medium">{g.label}</span>
                  <span className="font-mono text-[13px] text-muted">{g.stores.length}</span>
                </span>
                <span className="mt-2 line-clamp-2 text-[13px] text-faint">{g.stores.map((m) => m.name).join(" · ")}</span>
              </a>
            </li>
          ))}
        </ul>
      </section>

      {/* ── Gift cards ───────────────────────────────── */}
      <section className="wide mt-20 sm:mt-28">
        <div className="rounded-3xl bg-panel p-5 sm:p-10">
          <SectionHead
            title="Big store that doesn't take crypto?"
            note="Buy its gift card for crypto (from Coinsbee, Bitrefill, CoinGate and others), then pay with the card."
            more={{ href: "/gift-cards", label: `All ${GIFT_CARDS.length} brands` }}
          />
          <ul className="flex flex-wrap gap-2">
            {GIFT_CARDS.slice(0, 14).map((g) => (
              <li key={g.n}>
                <a href={`/gift-cards#${slug(g.n)}`} className="grid h-9 place-items-center rounded-full border border-line bg-paper px-3.5 text-sm hover:border-ink">
                  {g.n}
                </a>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* ── How it works ─────────────────────────────── */}
      <section className="wide mt-20 sm:mt-28">
        <SectionHead title="How it works" more={{ href: "/coming", label: "What's coming next" }} />
        <ol className="relative ml-4 border-l border-line">
          {steps.map(([t, d], i) => (
            <li key={t} className={`relative pl-9 ${i < steps.length - 1 ? "pb-8" : ""}`}>
              <span className="absolute -left-4 top-0 grid size-8 place-items-center rounded-full border border-line bg-panel font-mono text-[12px] text-signal-ink">
                0{i + 1}
              </span>
              <p className="pt-1 text-[17px] font-medium">{t}</p>
              <p className="mt-1 max-w-[60ch] text-[15px] text-muted">{d}</p>
            </li>
          ))}
        </ol>
      </section>
    </main>
  );
}
