import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { SectionHead, StoreList } from "@/components/Parts";
import { ProductCard } from "@/components/ProductCard";
import { GROUP_LABEL, evidenceNote, fmtDate, loadProducts, networkName, pays, slug, weakEvidence } from "@/lib/catalog";
import { canBuy } from "@/lib/products";
import { KIND_LABEL, MERCHANTS, STATUS_HELP, STATUS_LABEL } from "@/lib/merchants";

export const dynamicParams = false;

export function generateStaticParams() {
  return MERCHANTS.map((m) => ({ slug: slug(m.domain) }));
}

const find = (s: string) => MERCHANTS.find((m) => slug(m.domain) === s);

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const m = find((await params).slug);
  if (!m) return {};
  return { title: `${m.name}: pay with crypto`, description: `How ${m.name} (${m.domain}) takes crypto: ${pays(m)}. Where we found it, and how to check.` };
}

// merchant.how is "url — note; url — note" or plain notes; turn it into evidence lines.
// A note with no page of its own was seen on the store's site, so it links to the store's homepage;
// unless the note says it was the homepage or footer, a line says no direct page was kept.
function evidence(how: string, home: string) {
  return how
    .split(";")
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => {
      const [a, ...rest] = s.split(" — ");
      const own = /^https?:\/\//.test(a);
      const note = own ? rest.join(" — ") || "payment page" : s;
      const url = own ? a : home;
      return {
        url,
        note: evidenceNote(note),
        weak: weakEvidence(note, own ? a : null),
        noPage: !own && !/homepage|footer/i.test(note),
      };
    });
}

export default async function StorePage({ params }: { params: Promise<{ slug: string }> }) {
  const m = find((await params).slug);
  if (!m) notFound();

  const data = loadProducts();
  const si = data.stores.findIndex((s) => s.domain === m.domain);
  const store = data.stores[si];
  const products = si < 0 ? [] : data.products.filter((p) => p.s === si).sort((a, b) => Number(b.a) - Number(a.a) || Number(!!b.m) - Number(!!a.m));
  const shown = products.slice(0, 24);
  const same = MERCHANTS.filter((x) => x.group === m.group && x.domain !== m.domain).slice(0, 6);
  const group = GROUP_LABEL[m.group] ?? m.group;

  const facts: [string, React.ReactNode][] = [
    ["Pays with", pays(m)],
    ...(networkName(m.network ?? "") ? [["Network", networkName(m.network ?? "")] as [string, string]] : []),
    ["Category", <a key="c" href={`/stores?c=${slug(m.group)}`} className="link">{group}</a>],
    ["Sells", `${m.category}${KIND_LABEL[m.kind] && m.kind !== "online" ? ` · ${KIND_LABEL[m.kind]}` : ""}`],
    ["Status", <span key="s" title={STATUS_HELP[m.status]}><span className="text-pass">●</span> {STATUS_LABEL[m.status]}{m.checked ? ` ${fmtDate(m.checked)}` : " (date not recorded)"}</span>],
  ];

  return (
    <main className="wide pt-8 sm:pt-12">
      <nav aria-label="Breadcrumb" className="meta -my-2.5 flex flex-wrap items-center gap-x-1.5">
        <a href="/stores" className="link py-2.5">Stores</a>
        <span aria-hidden>/</span>
        <a href={`/stores?c=${slug(m.group)}`} className="link py-2.5">{group}</a>
      </nav>

      <div className="mt-4 grid gap-8 lg:grid-cols-[minmax(0,1fr)_22rem] lg:gap-12">
        <div>
          <h1 className="text-[34px] font-semibold leading-tight tracking-[-0.02em] sm:text-[46px]">{m.name}</h1>
          <p className="meta mt-1">{m.domain}</p>

          <dl className="mt-6 divide-y divide-line border-y border-line">
            {facts.map(([k, v]) => (
              <div key={k} className="grid grid-cols-[7rem_minmax(0,1fr)] gap-4 py-3 text-[15px] sm:grid-cols-[9rem_minmax(0,1fr)]">
                <dt className="meta pt-0.5">{k}</dt>
                <dd>{v}</dd>
              </div>
            ))}
          </dl>
        </div>

        <aside className="flex flex-col gap-4 self-start rounded-2xl border border-line bg-panel p-5">
          <a
            href={m.url}
            rel="nofollow noopener noreferrer"
            target="_blank"
            className="grid h-12 place-items-center rounded-xl bg-signal font-medium text-white"
          >
            Visit {m.domain} ↗
          </a>
          <div>
            <p className="meta">Where we saw crypto</p>
            <ul className="mt-2 flex flex-col gap-2 text-sm">
              {evidence(m.how, m.url).map((e, i) => (
                <li key={i} className="break-words">
                  <a href={e.url} rel="nofollow noopener noreferrer" target="_blank" className="link">
                    {e.note}
                  </a>
                  {e.weak && <span className="meta block">Old news or blog post, not the store&apos;s payment page. Check the checkout yourself.</span>}
                  {e.noPage && !e.weak && <span className="meta block">Seen on the store&apos;s site; we kept no direct page. Check the checkout yourself.</span>}
                </li>
              ))}
            </ul>
          </div>
          <p className="meta">Crypto payments can&apos;t be reversed. Check the domain and the amount on the checkout before paying.</p>
        </aside>
      </div>

      {store && products.length > 0 && (
        <section className="mt-14">
          <SectionHead
            title={canBuy(store) ? "Buy from this store" : "Products"}
            note={
              store.down
                ? `The store's site was not responding when we checked (${fmtDate(store.down)}). Buying is paused.`
                : canBuy(store)
                  ? "“Buy” opens their checkout with the item in the cart."
                  : undefined
            }
            more={products.length > shown.length ? { href: `/search?q=${encodeURIComponent(store.name)}`, label: `All ${products.length} products` } : undefined}
          />
          <ul className="grid grid-cols-2 gap-x-3 gap-y-9 md:grid-cols-3">
            {shown.map((p) => (
              <ProductCard key={p.u} p={p} store={store} showStore={false} />
            ))}
          </ul>
        </section>
      )}

      {same.length > 0 && (
        <section className="mt-14">
          <SectionHead title={`More in ${group}`} more={{ href: `/stores?c=${slug(m.group)}`, label: "All in this category" }} />
          <StoreList stores={same} />
        </section>
      )}
    </main>
  );
}
