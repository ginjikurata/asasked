// Turns the raw feeds in ../research/feeds/*.json into public/products.json,
// the small static file the home page search loads in the browser.
// Only stores that are verified=yes in lib/merchants.json are included.
// On a host without the research folder, the committed public/products.json is kept as is.
import { readFileSync, readdirSync, writeFileSync, existsSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const feedDir = process.env.FEEDS_DIR ?? join(here, "../../research/feeds");
const out = join(here, "../public/products.json");
const files = existsSync(feedDir) ? readdirSync(feedDir).filter((f) => f.endsWith(".json")) : [];
if (!files.length) {
  if (!existsSync(out)) { console.error(`no feeds in ${feedDir} and no public/products.json`); process.exit(1); }
  console.log("no feeds found, keeping existing public/products.json");
  process.exit(0);
}
// Stores where we checked by hand that /checkout/?add-to-cart=<id> puts the item in the cart
// AND a crypto payment method shows on that checkout (checked 2026-11-18). Only these get a
// "Buy" button; the others stay plain links to the product page.
const CRYPTO_CHECKOUT = {
  "satoshitcg.com": { cart: "https://satoshitcg.com/checkout/?add-to-cart=", via: "the store's own crypto checkout" },
  "bottegasenatore.com": { cart: "https://www.bottegasenatore.com/checkout/?add-to-cart=", via: "BitPay" },
};
// Stores whose site did not respond when we last checked (date). Their Buy buttons and home-page shelf
// are hidden until the date is removed here. satoshitcg.com answered 522 on 2026-11-27.
const DOWN = { "satoshitcg.com": "2026-11-27" };
// Store-wide product type for stores that leave it empty.
const DEFAULT_TYPE = { "satoshitcg.com": "Trading cards" };

const merchants = JSON.parse(readFileSync(join(here, "../lib/merchants.json"), "utf8"));
const byDomain = new Map(merchants.map((m) => [m.domain, m]));

const ENT = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " ", ndash: "–", mdash: "—", hellip: "…", rsquo: "’", lsquo: "‘", rdquo: "”", ldquo: "“", trade: "™", reg: "®", copy: "©" };
function clean(s) {
  return String(s ?? "")
    .replace(/<[^>]*>/g, " ")
    .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n)))
    .replace(/&#x([0-9a-f]+);/gi, (_, n) => String.fromCodePoint(parseInt(n, 16)))
    .replace(/&([a-z]+);/gi, (m, n) => ENT[n.toLowerCase()] ?? m)
    .replace(/\s+/g, " ")
    .trim();
}

function shopify(feed, m) {
  const currency = feed.currency ?? null;
  return feed.items.map((p) => {
    const vs = p.variants ?? [];
    const prices = vs.map((v) => Number(v.price)).filter((n) => n > 0);
    return {
      t: clean(p.title),
      p: prices.length ? Math.min(...prices) : null,
      c: currency,
      a: vs.some((v) => v.available),
      u: `${m.url.replace(/\/$/, "")}/products/${p.handle}`,
      k: clean(p.product_type),
      // Photo copied by scripts/products-images.mjs (hot-tent.com only for now).
      ...(existsSync(join(here, "../public/p", feed.domain, `${p.id}.jpg`)) ? { m: `/p/${feed.domain}/${p.id}.jpg` } : {}),
    };
  });
}

// Variable products: [[variationId, "Size 41", price?, inStock?], ...] with the shop's readable term names.
// price and inStock are there when the fetcher got the option itself (scripts/products-fetch.mjs).
function options(p) {
  if (p.type !== "variable" || !p.variations?.length) return undefined;
  const names = new Map();
  for (const a of p.attributes ?? []) for (const t of a.terms ?? []) names.set(`${a.name}|${t.slug}`, clean(t.name));
  const out = p.variations.map((v) => {
    const label = v.attributes.map((a) => names.get(`${a.name}|${a.value}`) ?? clean(a.value)).join(" / ");
    const o = v.offer;
    const price = o && Number(o.price) > 0 ? Number(o.price) / 10 ** (o.minor ?? 2) : null;
    return o ? [v.id, label, price, Boolean(o.inStock && price)] : [v.id, label];
  });
  // Sizes in number order (39, 40, 41), not the order the shop happened to list them.
  if (out.every((o) => /^\d+(?:[.,]\d+)?$/.test(o[1]))) out.sort((a, b) => Number(a[1].replace(",", ".")) - Number(b[1].replace(",", ".")));
  return out;
}

function woo(feed) {
  return feed.items.map((p) => {
    const pr = p.prices ?? {};
    const raw = Number(pr.price ?? pr.price_range?.min_amount);
    const v = options(p);
    // A variable product's own price can be stale (Bottega lists 390, every size checks out at 483):
    // when the options' prices are known, the listing shows the cheapest one in stock.
    const known = (v ?? []).filter((o) => o[3]).map((o) => o[2]);
    return {
      i: p.id,
      v,
      t: clean(p.name),
      p: known.length ? Math.min(...known) : raw > 0 ? raw / 10 ** (pr.currency_minor_unit ?? 2) : null,
      c: pr.currency_code ?? null,
      a: Boolean(p.is_in_stock),
      u: p.permalink,
      k: clean(p.categories?.[0]?.name),
      ...(existsSync(join(here, "../public/p", feed.domain, `${p.id}.jpg`)) ? { m: `/p/${feed.domain}/${p.id}.jpg` } : {}),
    };
  });
}

const stores = [];
const products = [];
for (const f of files.sort()) {
  const feed = JSON.parse(readFileSync(join(feedDir, f), "utf8"));
  const m = byDomain.get(feed.domain);
  if (!m) { console.log(`skip ${feed.domain}: not a verified store`); continue; }
  const rows = (feed.kind === "shopify" ? shopify(feed, m) : woo(feed))
    .filter((r) => r.t && r.u && r.p !== null);
  if (!rows.length) continue;
  const s = stores.length;
  const cc = feed.kind === "woo" ? CRYPTO_CHECKOUT[m.domain] : undefined;
  stores.push({ name: m.name, domain: m.domain, url: m.url, payment: m.payment, fetched: feed.fetched, ...(cc ?? {}), ...(DOWN[m.domain] ? { down: DOWN[m.domain] } : {}) });
  const k0 = DEFAULT_TYPE[m.domain];
  for (const { i, v, ...r } of rows) {
    if (!r.k && k0) r.k = k0;
    products.push(cc ? { ...r, s, i, ...(v ? { v } : {}) } : { ...r, s });
  }
  console.log(`${m.name}: ${rows.length}`);
}

mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, JSON.stringify({ built: new Date().toISOString(), stores, products }));
console.log(`${products.length} products from ${stores.length} stores → public/products.json`);
