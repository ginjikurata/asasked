// Copies one small product photo per item into public/p/<domain>/<id>.jpg for the stores below.
// Photos are served from lab itself, so a visitor's browser never loads anything from the stores
// until they click through. Run by hand after products:fetch; files already on disk are kept.
// products-to-json.mjs links a photo only if its file exists.
// The image host's robots.txt is read first; a 403 or 429 stops that store at once, no retries.
// Usage: node scripts/products-images.mjs [domain ...]   (no args = all stores below)
import { readFileSync, readdirSync, writeFileSync, existsSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { robotsRules, allowed } from "./robots.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const feedDir = process.env.FEEDS_DIR ?? join(here, "../../research/feeds");
// hot-tent.com (RBM Outdoors) added 2026-11-27: no Buy button, photos only.
const STORES = ["bottegasenatore.com", "satoshitcg.com", "hot-tent.com"];
const UA = "AsAskedLabBot/0.1 (+https://lab.asasked.dev; finds stores that accept crypto)";
const sleep = (ms) => new Promise((ok) => setTimeout(ok, ms));

// Woo: smallest srcset entry at least 400px wide, else the main image.
function pickWoo(img) {
  const set = String(img.srcset ?? "")
    .split(",")
    .map((s) => s.trim().split(/\s+/))
    .map(([url, w]) => ({ url, w: parseInt(w, 10) }))
    .filter((x) => x.url && x.w >= 400)
    .sort((a, b) => a.w - b.w);
  const url = set[0]?.url ?? img.thumbnail ?? img.src;
  return /\.jpe?g(\?|$)/i.test(url) ? url : null;
}

// Shopify CDN resizes and converts on request: 600px wide JPEG (about 35 KB), also for PNG/WebP sources.
function pickShopify(img) {
  if (!img?.src) return null;
  const u = new URL(img.src);
  u.searchParams.set("width", "600");
  u.searchParams.set("format", "jpg");
  return u.href;
}

const robotsCache = new Map();
async function hostAllows(url) {
  const u = new URL(url);
  if (!robotsCache.has(u.host)) {
    let rules = [];
    try {
      const r = await fetch(`${u.origin}/robots.txt`, { headers: { "user-agent": UA } });
      if (r.status === 403 || r.status === 429) rules = [{ allow: false, path: "/" }];
      else if (r.ok) rules = robotsRules(await r.text());
    } catch {}
    robotsCache.set(u.host, rules);
  }
  return allowed(robotsCache.get(u.host), u.pathname);
}

const only = process.argv.slice(2);
for (const f of readdirSync(feedDir).filter((f) => f.endsWith(".json"))) {
  const feed = JSON.parse(readFileSync(join(feedDir, f), "utf8"));
  if (!STORES.includes(feed.domain) || (only.length && !only.includes(feed.domain))) continue;
  const shopify = feed.kind === "shopify";
  const dir = join(here, "../public/p", feed.domain);
  mkdirSync(dir, { recursive: true });
  let got = 0, kept = 0, none = 0, failed = 0;
  for (const p of feed.items) {
    // Shopify: only items the catalog lists (a price above 0), as in products-to-json.mjs.
    if (shopify && !(p.variants ?? []).some((v) => Number(v.price) > 0)) continue;
    const file = join(dir, `${p.id}.jpg`);
    if (existsSync(file)) { kept++; continue; }
    const img = p.images?.[0];
    const url = img && (shopify ? pickShopify(img) : pickWoo(img));
    if (!url) { none++; continue; }
    if (!(await hostAllows(url))) { console.log(`robots.txt disallows ${url}, store skipped`); break; }
    const r = await fetch(url, { headers: { "user-agent": UA, accept: "image/jpeg" } });
    if (r.status === 403 || r.status === 429) { console.log(`HTTP ${r.status} on ${url}, store skipped`); break; }
    if (!r.ok || !String(r.headers.get("content-type")).startsWith("image/jpeg")) { console.log(`skip ${url}: ${r.status}`); failed++; continue; }
    writeFileSync(file, Buffer.from(await r.arrayBuffer()));
    got++;
    await sleep(shopify ? 1000 : 300);
  }
  console.log(`${feed.domain}: ${got} new, ${kept} kept, ${none} without a photo, ${failed} failed`);
}
