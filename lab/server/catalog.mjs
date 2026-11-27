// The public catalog (products.json, the same file the site serves) and the guard check,
// using the site's own lib/intent.ts so the site and agents get the same answers.
import { readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { checkProduct, isAccessory, parseIntent, relevance, searchText, termMatches } from "../lib/intent.ts";

const file = process.env.LAB_PRODUCTS ?? join(import.meta.dirname, "../public/products.json");
export const ORIGIN = process.env.LAB_ORIGIN ?? "https://lab.asasked.dev";

let cache = { mtime: 0, data: null, index: [], byUrl: new Map() };

// Reloads when a deploy replaces products.json.
export function catalog() {
  const mtime = statSync(file).mtimeMs;
  if (mtime !== cache.mtime) {
    const data = JSON.parse(readFileSync(file, "utf8"));
    cache = {
      mtime,
      data,
      index: data.products.map((p) => searchText(p, data.stores[p.s])),
      byUrl: new Map(data.products.map((p) => [p.u, p])),
    };
  }
  return cache;
}

const optionOut = ([id, label, price, inStock]) => ({ id, label, price: price ?? null, in_stock: inStock ?? null });

export function productOut(p, { full = false } = {}) {
  const store = catalog().data.stores[p.s];
  const out = {
    url: p.u,
    title: p.t,
    type: p.k,
    store: store.name,
    store_domain: store.domain,
    price: p.p,
    currency: p.c,
    price_is_from: new Set((p.v ?? []).map((o) => o[2]).filter((x) => typeof x === "number")).size > 1,
    in_stock: p.a,
    options: (p.v ?? []).map(optionOut),
  };
  if (full) {
    out.photo = p.m ? `${ORIGIN}${p.m}` : null;
    out.payment = store.payment || null;
    out.payment_via = store.via ?? null;
    out.catalog_updated = store.fetched;
  }
  return out;
}

// The guard, plus a check of one chosen option when the agent names it.
export function check(p, request, optionLabel) {
  const { data } = catalog();
  const intent = parseIntent(request ?? "");
  const r = checkProduct(p, data.stores[p.s], intent);
  const good = [...r.good];
  const bad = [...r.bad];
  if (optionLabel) {
    const o = (p.v ?? []).find(([, l]) => l.toLowerCase() === String(optionLabel).toLowerCase());
    if (!o) bad.push(`no option "${optionLabel}"`);
    else {
      // The guard may already say so ("size 42 sold out"); don't repeat it.
      const said = [`size ${o[1].toLowerCase()} sold out`, `${o[1].toLowerCase()} sold out`];
      if (o[3] === false && !bad.some((b) => said.includes(b))) bad.push(`option ${o[1]} is sold out`);
      if (intent.budget !== undefined && typeof o[2] === "number" && (!p.c || p.c === "USD") && o[2] > intent.budget)
        bad.push(`option ${o[1]} costs $${o[2]}, over $${intent.budget}`);
    }
  }
  return { fits: bad.length === 0, good, bad, understood: intent };
}

export function search(query, { limit = 10, store, inStock = true } = {}) {
  const { data, index } = catalog();
  const intent = parseIntent(query ?? "");
  const rows = [];
  data.products.forEach((p, n) => {
    if (inStock && !p.a) return;
    if (store && data.stores[p.s].domain !== store) return;
    if (!intent.terms.every((w) => termMatches(w, index[n]))) return;
    rows.push({ p, c: checkProduct(p, data.stores[p.s], intent) });
  });
  // Fits first, then the item itself before things that only mention it ("Stove Jack"), accessories last.
  rows.sort(
    (a, b) =>
      a.c.bad.length - b.c.bad.length ||
      relevance(a.p, intent.terms) - relevance(b.p, intent.terms) ||
      Number(isAccessory(a.p)) - Number(isAccessory(b.p)),
  );
  return {
    understood: intent,
    total: rows.length,
    fitting: rows.filter((r) => r.c.fits).length,
    results: rows.slice(0, limit).map(({ p, c }) => ({ ...productOut(p), check: { fits: c.fits, good: c.good, bad: c.bad } })),
  };
}

export const product = (url) => catalog().byUrl.get(url) ?? null;

// All stores in the catalog (people checked each one by hand); those with product feeds are searchable.
const merchantsFile = process.env.LAB_MERCHANTS ?? join(import.meta.dirname, "../lib/merchants.json");
let merchants = { mtime: 0, list: [] };
export function stores() {
  const mtime = statSync(merchantsFile).mtimeMs;
  if (mtime !== merchants.mtime) merchants = { mtime, list: JSON.parse(readFileSync(merchantsFile, "utf8")).filter((m) => m.status === "yes") };
  const feeds = new Map(catalog().data.stores.map((s) => [s.domain, s]));
  const out = merchants.list.map((m) => ({
    name: m.name,
    domain: m.domain,
    url: m.url,
    category: m.group ?? m.category ?? null,
    online: m.kind !== "physical",
    payment: feeds.get(m.domain)?.payment || m.payment || null,
    via: feeds.get(m.domain)?.via ?? m.gateway ?? null,
    products_searchable: feeds.has(m.domain),
  }));
  for (const [domain, s] of feeds)
    if (!out.some((o) => o.domain === domain))
      out.push({ name: s.name, domain, url: s.url, category: null, online: true, payment: s.payment || null, via: s.via ?? null, products_searchable: true });
  return out;
}
