import type { Metadata } from "next";
import { Catalog } from "@/components/Catalog";
import { fmtDate, groups, loadProducts } from "@/lib/catalog";
import { MERCHANTS, lastChecked } from "@/lib/merchants";

export const metadata: Metadata = {
  title: "Stores that take crypto",
  description: `${MERCHANTS.length} online stores where we found signs they take crypto, each checked one by one.`,
};

export default function Stores() {
  // What each store sells, from its product types, so "tent" or "shoes" finds the store too.
  const data = loadProducts();
  const sells: Record<string, string> = {};
  data.stores.forEach((st, i) => {
    const kinds = new Set(data.products.filter((p) => p.s === i).map((p) => p.k.toLowerCase()).filter(Boolean));
    sells[st.domain] = [...kinds].join(" ");
  });
  const cats = groups().map((g) => ({ slug: g.slug, label: g.label, n: g.stores.length }));
  return (
    <main className="wide pt-10 sm:pt-14">
      <p className="meta">Last check {fmtDate(lastChecked())}</p>
      <h1 className="mt-2 text-[32px] font-semibold tracking-[-0.02em] sm:text-[42px]">All stores</h1>
      <p className="mt-2 mb-8 max-w-[60ch] text-muted">
        {MERCHANTS.length} stores where we found signs they take crypto: most on their own payment page or checkout, a few
        only in a news item or blog post. Open a store to see where we found it, and check the checkout before you pay.
      </p>
      <Catalog cats={cats} sells={sells} />
    </main>
  );
}
