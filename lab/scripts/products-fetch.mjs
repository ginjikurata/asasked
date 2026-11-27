// Downloads the public product feeds of stores in the catalog that expose one
// (Shopify /products.json, WooCommerce Store API) into ../research/feeds/<domain>.json.
// Runs one request at a time with a pause. A 403 or 429 means the store does not want us
// there: that store is skipped at once, with no retries.
// Honest User-Agent; robots.txt is read first and disallowed paths are not fetched.
// Usage: node scripts/products-fetch.mjs [domain ...]   (no args = all stores below)
import { mkdirSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { robotsRules, allowed } from "./robots.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const outDir = join(here, "../../research/feeds");
mkdirSync(outDir, { recursive: true });

// Stores with an open feed, checked 2026-11-18. Only domains that are verified=yes in merchants.csv.
export const FEEDS = [
  ["bottegasenatore.com", "woo"],
  ["satoshitcg.com", "woo"],
  ["crmjewelers.com", "shopify"],
  ["atheist.shoes", "shopify"],
  ["alexlexington.com", "shopify"],
  ["case-mate.com", "shopify"],
  ["coolwallet.io", "shopify"],
  ["djkit.com", "shopify"],
  ["growershouse.com", "shopify"],
  ["jewelryaffairs.com", "shopify"],
  ["lanieri.com", "shopify"],
  ["leibish.com", "shopify"],
  ["lindaslook.com", "shopify"],
  ["littlewildkid.store", "shopify"],
  ["maingear.com", "shopify"],
  ["mukorombolt.hu", "shopify"],
  ["outofthegreycoffee.com", "shopify"],
  ["raydin.store", "shopify"],
  ["shsilver.com", "shopify"],
  ["wristaficionado.com", "shopify"],
  ["hot-tent.com", "shopify"], // added 2026-11-21
];

const MAX_PAGES = 2; // Shopify: 250 per page; Woo: 100 per page. Enough for a trial.
const PAUSE_MS = 4000;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const UA = "AsAskedLabBot/0.1 (+https://lab.asasked.dev; finds stores that accept crypto)";

const blocked = (status) => Object.assign(new Error(`HTTP ${status}, store skipped`), { blocked: true });

async function robots(domain) {
  let res;
  try {
    res = await fetch(`https://${domain}/robots.txt`, { headers: { "user-agent": UA }, redirect: "follow" });
  } catch {
    return [];
  }
  if (res.status === 403 || res.status === 429) throw blocked(res.status);
  return res.ok ? robotsRules(await res.text()) : [];
}

async function get(url) {
  const res = await fetch(url, {
    headers: { "user-agent": UA, accept: "application/json" },
    redirect: "follow",
  });
  if (res.status === 403 || res.status === 429) throw blocked(res.status);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function fetchStore(domain, kind) {
  const rules = await robots(domain);
  const feedPath = kind === "shopify" ? "/products.json" : "/wp-json/wc/store/v1/products";
  if (!allowed(rules, feedPath)) throw new Error(`robots.txt disallows ${feedPath}`);
  await sleep(PAUSE_MS);
  const items = [];
  for (let page = 1; page <= MAX_PAGES; page++) {
    const url =
      kind === "shopify"
        ? `https://${domain}/products.json?limit=250&page=${page}`
        : `https://${domain}/wp-json/wc/store/v1/products?per_page=100&page=${page}`;
    const data = await get(url);
    const batch = kind === "shopify" ? data.products ?? [] : Array.isArray(data) ? data : [];
    items.push(...batch);
    await sleep(PAUSE_MS);
    if (batch.length < (kind === "shopify" ? 250 : 100)) break;
  }
  // Woo lists one price per product (the cheapest option). Each option's own price and stock
  // come from the variations themselves, 100 per request.
  if (kind === "woo") {
    const ids = items.flatMap((p) => (p.type === "variable" ? (p.variations ?? []).map((v) => v.id) : []));
    const byId = new Map();
    for (let i = 0; i < ids.length; i += 100) {
      const chunk = ids.slice(i, i + 100);
      const data = await get(`https://${domain}/wp-json/wc/store/v1/products?type=variation&per_page=100&include=${chunk.join(",")}`);
      for (const v of Array.isArray(data) ? data : []) byId.set(v.id, { price: v.prices?.price, minor: v.prices?.currency_minor_unit, inStock: v.is_in_stock });
      await sleep(PAUSE_MS);
    }
    for (const p of items) for (const v of p.variations ?? []) if (byId.has(v.id)) v.offer = byId.get(v.id);
  }
  // products.json has no currency; the store's cart endpoint and /meta.json do. Only paths robots.txt allows.
  let currency = null;
  if (kind === "shopify") {
    for (const path of ["/cart.js", "/meta.json"]) {
      if (currency || !allowed(rules, path)) continue;
      try { currency = (await get(`https://${domain}${path}`)).currency ?? null; } catch (e) { if (e.blocked) throw e; }
      await sleep(PAUSE_MS);
    }
  }
  return { items, currency };
}

const only = process.argv.slice(2);
for (const [domain, kind] of FEEDS) {
  if (only.length && !only.includes(domain)) continue;
  process.stdout.write(`${domain} (${kind}) … `);
  try {
    const { items, currency } = await fetchStore(domain, kind);
    writeFileSync(
      join(outDir, `${domain}.json`),
      JSON.stringify({ domain, kind, currency, fetched: new Date().toISOString(), items }),
    );
    console.log(`${items.length} items`);
  } catch (e) {
    console.log(`failed: ${e.message}`);
  }
}
