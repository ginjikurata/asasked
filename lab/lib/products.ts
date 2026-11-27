// Shared types and helpers for public/products.json (built by scripts/products-to-json.mjs).

// cart/via are set only for stores where we checked that the cart link works and crypto shows at checkout.
// down = date we last found the store's site not responding; Buy buttons are hidden while it is set.
export type Store = { name: string; domain: string; url: string; payment: string; fetched: string; cart?: string; via?: string; down?: string };
// A Buy button is shown only for stores whose cart link we checked and whose site is up.
export const canBuy = (s: Store | undefined) => Boolean(s?.cart && !s.down);
// i = store's product id, m = local photo path.
// v = [[variationId, label, price?, inStock?]] for products with sizes/options; price and inStock are
// known for WooCommerce stores, where one product's options can cost different amounts.
export type Product = {
  t: string;
  p: number;
  c: string | null;
  a: boolean;
  u: string;
  k: string;
  s: number;
  i?: number;
  v?: Option[];
  m?: string;
};
export type Option = [id: number, label: string, price?: number | null, inStock?: boolean];
export type Data = { built: string; stores: Store[]; products: Product[] };

export function money(n: number, c: string | null) {
  if (!c) return n.toLocaleString("en-US");
  try {
    const d = n % 1 ? 2 : 0; // "$1,582.20", never "$1,582.2"
    return new Intl.NumberFormat("en-US", { style: "currency", currency: c, minimumFractionDigits: d, maximumFractionDigits: d }).format(n);
  } catch {
    return `${n.toLocaleString("en-US")} ${c}`;
  }
}

// "from $X" only when the options one can still buy differ in price (a sold-out size doesn't count).
export function variesInPrice(p: Product) {
  const left = (p.v ?? []).filter((o) => o[3] !== false);
  const ps = new Set((left.length ? left : p.v ?? []).map((o) => o[2]).filter((x): x is number => typeof x === "number"));
  return ps.size > 1;
}

export function price(p: Product) {
  return (variesInPrice(p) ? "from " : "") + money(p.p, p.c);
}

// Store product titles are long ("Cerimonia Black Patent Refinement, Lightness, and Elegance").
// Cards show the part before the first comma or dash; the full title stays in the link's title.
export function shortTitle(t: string) {
  // A comma between numbers ("Coody 17.2, 13.6 m²") is part of the name, not the end of it.
  const cut = t.split(/\s[–—-]\s|(?<!\d),\s|,\s(?!\d)/)[0];
  return cut.length >= 6 ? cut : t;
}
