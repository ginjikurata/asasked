// Finds signs of crypto payment on stores' own public pages and writes candidates for a human to check.
// Nothing here publishes anything: output goes to research/candidates.csv, and a store reaches the site
// only after a person marks it "yes" in research/merchants.csv (see DISCOVERY.md).
//
// Usage:
//   node scripts/discover.mjs known            re-check every store in research/merchants.csv (accuracy test)
//   node scripts/discover.mjs bitpay           BitPay directory entries that are not in merchants.csv yet
//   node scripts/discover.mjs coingate         CoinGate "Online Stores" (Pay Direct) not in merchants.csv yet
//   node scripts/discover.mjs domain a.com b.com   check given domains
//   node scripts/discover.mjs recheck          monthly re-check of published ("yes") stores -> research/recheck.csv
// Options: --limit N, --out path (--out is not used by recheck)
//
// Rules: honest User-Agent, robots.txt respected, one request at a time per site with a pause,
// public pages only (home, sitemap, up to 3 payment/FAQ pages). 403/429/captcha/bot-wall => "blocked", skipped.
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { robotsRules, allowed } from "./robots.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const RESEARCH = join(here, "../../research");
const UA = "AsAskedLabBot/0.1 (+https://lab.asasked.dev; finds stores that accept crypto)";
const PAUSE_MS = 2500; // between requests to the same site
const PARALLEL_SITES = 6;
const TIMEOUT_MS = 20000;
const MAX_BYTES = 3_000_000;

// ---------- csv ----------
function parseCsv(text) {
  const rows = [];
  let row = [], cell = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { cell += '"'; i++; }
      else if (c === '"') quoted = false;
      else cell += c;
    } else if (c === '"') quoted = true;
    else if (c === ",") { row.push(cell); cell = ""; }
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(cell); rows.push(row); row = []; cell = "";
    } else cell += c;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  const [head, ...body] = rows.filter((r) => r.some((v) => v.trim()));
  return body.map((r) => Object.fromEntries(head.map((h, i) => [h, r[i] ?? ""])));
}
const esc = (v) => (/[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v));
const toCsv = (rows, cols) => [cols.join(","), ...rows.map((r) => cols.map((c) => esc(r[c] ?? "")).join(","))].join("\n") + "\n";

// ---------- signals ----------
// Strong: the store's own pages load or link a crypto checkout, or show Shopify's crypto payment icons.
const GATEWAYS = [
  ["BitPay", /(?:\/\/|\.)bitpay\.com/i],
  ["Coinbase Commerce", /commerce\.coinbase\.com|pay\.coinbase\.com/i],
  ["NOWPayments", /nowpayments\.io/i],
  ["CoinGate", /coingate\.com/i],
  ["Triple-A", /triple-a\.io/i],
  ["Helio", /(?:\/\/|\.)hel\.io|helio\.co/i],
  ["Confirmo", /confirmo\.net/i],
  ["CoinPayments", /coinpayments\.net/i],
  ["OpenNode", /opennode\.com/i],
  ["BTCPay", /btcpay(?:server)?\.[a-z]+/i],
  ["Plisio", /plisio\.net/i],
  ["Cryptomus", /cryptomus\.com/i],
  ["xMoney", /xmoney\.com/i],
];
const ICONS = [
  ["Shopify USDC icon", /pi-usdc/i],
  ["Shopify Bitcoin icon", /pi-bitcoin/i],
  ["Shopify Ethereum icon", /pi-ethereum/i],
  ["Shopify crypto icon", /pi-(?:dogecoin|litecoin|bitcoin-cash|solana)/i],
];
// Weak: only words on the page.
const WORDS = /pay(?:ing)?\s+(?:with|in|by)\s+(?:bitcoin|crypto(?:currency|currencies)?|usdc|stablecoins?)|accept(?:s|ing)?\s+(?:bitcoin|crypto(?:currency|currencies)?|usdc|stablecoins?)|cryptocurrency\s+payments?|crypto\s+payments?\s+(?:accepted|available)|bitcoin\s+accepted/i;
// Pages worth a second look, found among the home page's same-site links.
const PAY_LINK = /crypto|bitcoin|btc|usdc|pay-?with|payment|faq|help|support|polic/i;
// Pages that name vendors without meaning the store takes crypto.
const SKIP_PAGE = /cookie|privacy|gdpr|terms|legal|imprint|impressum/i;
// The store says plainly it does not take crypto: that beats any other signal.
const NEGATIVE = /(?:do(?:es)?\s+not|don['’]t|no\s+longer|cannot|can['’]t)\s+(?:currently\s+)?(?:accept|support|take)\s+(?:any\s+)?(?:bitcoin|crypto(?:currency|currencies)?|btc)(?:\s+payments?)?/i;
// Gateway or coin named anywhere in the markup (alt text, image names, footer text): weak, a person checks.
const NAMES = [
  ["names BitPay", /\bbitpay\b/i],
  ["names Coinbase Commerce", /coinbase\s*commerce/i],
  ["names NOWPayments", /\bnowpayments\b/i],
  ["names CoinGate", /\bcoingate\b/i],
  ["names Solana Pay", /solana\s*pay/i],
  ["names USDC", /\busdc\b/i],
];
const BOT_WALL = /cf-chl-|challenge-platform|just a moment\.\.\.|attention required|captcha|px-captcha|datadome|perimeterx|incapsula|are you a robot|access denied/i;

function scan(html, url) {
  const found = [];
  // Look only at markup that can carry checkout links: attributes, scripts, svg ids; strip big inline JSON noise lightly.
  for (const [name, re] of GATEWAYS) if (re.test(html)) found.push({ kind: "strong", name, url });
  for (const [name, re] of ICONS) if (re.test(html)) found.push({ kind: "strong", name, url });
  const text = html.replace(/<script[\s\S]*?<\/script>|<style[\s\S]*?<\/style>/gi, " ").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
  const neg = text.match(NEGATIVE);
  if (neg) found.push({ kind: "negative", name: `says no: "${neg[0].slice(0, 60)}"`, url });
  const m = text.match(WORDS);
  if (m) found.push({ kind: "weak", name: `text: "${m[0].slice(0, 60)}"`, url });
  const markup = html.replace(/<style[\s\S]*?<\/style>/gi, " ");
  for (const [name, re] of NAMES) if (re.test(markup)) found.push({ kind: "weak", name, url });
  return found;
}

// ---------- polite fetching ----------
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function get(url) {
  const res = await fetch(url, {
    headers: { "User-Agent": UA, Accept: "text/html,application/xhtml+xml,*/*;q=0.5", "Accept-Language": "en" },
    redirect: "follow",
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  const reader = res.body?.getReader();
  let size = 0; const parts = [];
  if (reader) {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.length; parts.push(value);
      if (size > MAX_BYTES) { await reader.cancel(); break; }
    }
  }
  return { status: res.status, url: res.url, body: Buffer.concat(parts).toString("utf8") };
}

// Reads the sitemap (and at most 3 child sitemaps, preferring page/cms ones) and returns crypto-looking URLs.
async function sitemapCryptoPages(base, rules, listed) {
  const CRYPTO = /crypto|bitcoin|btc|pay-?with-?(?:bitcoin|crypto|usdc)|usdc|stablecoin/i;
  const locs = (xml) => [...xml.matchAll(/<loc>\s*([^<\s]+)\s*<\/loc>/gi)].map((m) => m[1].replace(/&amp;/g, "&"));
  const first = listed[0] ?? `${base}/sitemap.xml`;
  const hits = [];
  try {
    if (!allowed(rules, new URL(first).pathname)) return [];
    await sleep(PAUSE_MS);
    const r = await get(first);
    if (r.status !== 200) return [];
    let urls = locs(r.body);
    if (/<sitemapindex/i.test(r.body)) {
      const kids = urls.sort((a, b) => Number(/page|cms|info|content/i.test(b)) - Number(/page|cms|info|content/i.test(a))).slice(0, 3);
      urls = [];
      for (const k of kids) {
        await sleep(PAUSE_MS);
        try { const c = await get(k); if (c.status === 200) urls.push(...locs(c.body)); } catch { /* skip */ }
      }
    }
    for (const u of urls) if (CRYPTO.test(new URL(u, base).pathname)) hits.push(u);
  } catch { /* no sitemap */ }
  return hits.slice(0, 5);
}

async function checkSite(domain) {
  const out = { domain, result: "none", signals: "", evidence_url: "", http: "", pages: 0, note: "" };
  const base = `https://${domain}`;
  let rules = [], sitemaps = [];
  try {
    const r = await get(`${base}/robots.txt`);
    if (r.status === 200 && !/<html/i.test(r.body.slice(0, 500))) {
      rules = robotsRules(r.body);
      sitemaps = [...r.body.matchAll(/^\s*sitemap:\s*(\S+)/gim)].map((m) => m[1]);
    }
  } catch { /* no robots.txt reachable: treat as no rules */ }
  if (!allowed(rules, "/")) { out.result = "robots"; out.note = "robots.txt disallows the home page"; return out; }
  await sleep(PAUSE_MS);

  let home;
  try { home = await get(`${base}/`); } catch (e) { out.result = "error"; out.note = String(e.cause?.code ?? e.name ?? e).slice(0, 80); return out; }
  out.http = String(home.status); out.pages = 1;
  if ([401, 403, 429, 503].includes(home.status) || (BOT_WALL.test(home.body.slice(0, 20000)) && home.body.length < 60000)) {
    out.result = "blocked"; out.note = `home page answered ${home.status}, bot protection or rate limit`; return out;
  }
  if (home.status >= 400) { out.result = "error"; out.note = `home page answered ${home.status}`; return out; }

  const signals = scan(home.body, home.url);
  // Follow up to two same-site links that look like payment/crypto/FAQ pages.
  const host = new URL(home.url).host.replace(/^www\./, "");
  const links = [...home.body.matchAll(/href\s*=\s*["']([^"'#]+)["']/gi)].map((m) => m[1]);
  const picks = [];
  for (const l of links) {
    let u; try { u = new URL(l, home.url); } catch { continue; }
    if (u.host.replace(/^www\./, "") !== host || !/^https?:$/.test(u.protocol)) continue;
    if (!PAY_LINK.test(u.pathname) || /\.(?:jpg|png|svg|css|js|pdf)$/i.test(u.pathname)) continue;
    // Cookie and privacy pages list every tracker and vendor, BitPay included; they prove nothing about checkout.
    if (SKIP_PAGE.test(u.pathname)) continue;
    const key = u.origin + u.pathname;
    if (!picks.includes(key) && key !== home.url) picks.push(key);
  }
  // Many stores keep the crypto page out of the menu; the sitemap often lists it.
  for (const u of await sitemapCryptoPages(base, rules, sitemaps)) if (!picks.includes(u)) picks.push(u);
  // Crypto-specific pages first.
  const rank = (u) => (/crypto|bitcoin|btc|usdc/i.test(u) ? 2 : /pay/i.test(u) ? 1 : 0);
  picks.sort((a, b) => rank(b) - rank(a));
  for (const p of picks.slice(0, 3)) {
    if (!allowed(rules, new URL(p).pathname)) continue;
    await sleep(PAUSE_MS);
    try {
      const r = await get(p); out.pages++;
      if (r.status === 200) signals.push(...scan(r.body, r.url));
    } catch { /* one page failing is fine */ }
  }

  const strong = signals.filter((s) => s.kind === "strong");
  const pick = signals.find((s) => s.kind === "negative") ?? strong[0] ?? signals[0];
  const negative = signals.filter((s) => s.kind === "negative");
  out.result = negative.length ? "negative" : strong.length ? "strong" : signals.length ? "weak" : "none";
  out.signals = [...new Set(signals.map((s) => s.name))].join("; ");
  out.evidence_url = pick?.url ?? "";
  return out;
}

async function pool(items, n, fn) {
  const res = new Array(items.length); let i = 0, done = 0;
  await Promise.all(Array.from({ length: n }, async () => {
    while (i < items.length) {
      const k = i++; res[k] = await fn(items[k]);
      done++; if (done % 10 === 0 || done === items.length) console.error(`${done}/${items.length}`);
    }
  }));
  return res;
}

// ---------- sources ----------
const known = () => parseCsv(readFileSync(join(RESEARCH, "merchants.csv"), "utf8"));
const norm = (d) => d.trim().toLowerCase().replace(/^https?:\/\//, "").replace(/^www\./, "").replace(/\/.*$/, "");

const NOT_MERCHANT = /(?:^|\.)(?:bitpay\.com|bitcore\.io|framer\.com|framerusercontent\.com|framer\.website|gstatic\.com|googleapis\.com|apple\.com|google\.com|facebook\.com|twitter\.com|x\.com|instagram\.com|linkedin\.com|youtube\.com|tiktok\.com|reddit\.com|t\.me|discord\.gg|medium\.com|github\.com)$/i;

async function bitpayCandidates() {
  const have = new Set(known().map((m) => norm(m.domain)));
  const haveNames = new Set(known().map((m) => m.name.trim().toLowerCase()));
  const dir = parseCsv(readFileSync(join(RESEARCH, "bitpay_directory.csv"), "utf8")).filter((r) => r.type === "direct_pay");
  const todo = dir.filter((r) => !haveNames.has(r.name.trim().toLowerCase()));
  const found = [];
  for (const r of todo) {
    // The directory page links to the merchant's own site; take the first external, non-BitPay link.
    try {
      const page = await get(r.url);
      // Only real <a> links; BitPay's own site, its Framer hosting, fonts and social links are not the merchant.
      const ext = [...page.body.matchAll(/<a\b[^>]*\bhref\s*=\s*["'](https?:\/\/[^"']+)["']/gi)].map((m) => m[1])
        .map((u) => { try { return new URL(u); } catch { return null; } })
        .filter((u) => u && !NOT_MERCHANT.test(u.host));
      // Prefer a link whose host contains the directory slug (taaboimports -> www.taaboimports.com).
      const slug = r.slug.replace(/[^a-z0-9]/gi, "").toLowerCase();
      const best = ext.find((u) => slug && u.host.replace(/[^a-z0-9]/gi, "").toLowerCase().includes(slug)) ?? ext[0];
      const d = best ? norm(best.host) : "";
      if (d && !have.has(d)) found.push({ domain: d, name: r.name, source: "bitpay-directory" });
    } catch { /* skip */ }
    await sleep(PAUSE_MS);
  }
  console.error(`bitpay: ${todo.length} directory entries not in merchants.csv, ${found.length} new domains`);
  return found;
}

// CoinGate's public store list (coingate.com/stores), Online Stores category only: hosting, VPN and proxy
// services there have no cart to put an item in. Only "Pay Direct" cards count: "Gift Cards" cards
// (links under /gift-cards/) are CoinGate selling a gift card, not the store taking crypto.
const CG = "https://coingate.com";
const CG_CATEGORY = "/stores/category/online-stores";
const CG_NOT_STORE = new Set(["category", "page", "feed", "coingate-gift-cards"]);
const unhtml = (s) => s.replace(/<[^>]+>/g, " ").replace(/&amp;|&#0?38;/g, "&").replace(/&#8217;|&#0?39;/g, "'").replace(/\s+/g, " ").trim();

async function coingateCandidates(want) {
  const have = new Set(known().map((m) => norm(m.domain)));
  const haveNames = new Set(known().map((m) => m.name.trim().toLowerCase()));
  let rules = [];
  try { const r = await get(`${CG}/robots.txt`); if (r.status === 200) rules = robotsRules(r.body); } catch { /* none */ }
  if (!allowed(rules, `${CG_CATEGORY}/`)) { console.error("coingate: robots.txt disallows the store list"); return []; }

  // 1. Category pages: slug, name and tags of each card. Page 1 links the last page number.
  // (Nov 2026: page 1 links pages up to 5, but 4 and 5 answer 404, so the loop stops at the first non-200.)
  const cards = new Map();
  let last = 1, read = 0;
  for (let n = 1; n <= last; n++) {
    await sleep(PAUSE_MS);
    let page;
    try { page = await get(`${CG}${CG_CATEGORY}${n > 1 ? `/page/${n}` : ""}`); } catch { console.error(`coingate: page ${n} failed`); break; }
    if (page.status !== 200) { console.error(`coingate: page ${n} answered ${page.status}, stopping`); break; }
    read++;
    if (n === 1) last = Math.min(20, Math.max(1, ...[...page.body.matchAll(/online-stores\/page\/(\d+)/g)].map((m) => Number(m[1]))));
    for (const m of page.body.matchAll(/<a href="https:\/\/coingate\.com\/stores\/([a-z0-9-]+)\/?"[^>]*>([\s\S]*?)<\/a>/gi)) {
      const [, slug, inner] = m;
      if (CG_NOT_STORE.has(slug) || cards.has(slug)) continue;
      const tags = [...inner.matchAll(/<div class="shrink-0[^"]*">([\s\S]*?)<\/div>/gi)].map((t) => unhtml(t[1]));
      const name = unhtml(inner.match(/<h5[^>]*>([\s\S]*?)<\/h5>/i)?.[1] ?? slug);
      cards.set(slug, { name, tags });
    }
  }
  const direct = [...cards].filter(([, c]) => c.tags.includes("Pay Direct") && !/^coingate\b/i.test(c.name));
  const todo = direct.filter(([, c]) => !haveNames.has(c.name.toLowerCase()));

  // 2. Each store page links the store's own site; take that domain.
  const found = [];
  for (const [slug, c] of todo) {
    if (found.length >= want) break;
    if (!allowed(rules, `/stores/${slug}`)) continue;
    await sleep(PAUSE_MS);
    try {
      const page = await get(`${CG}/stores/${slug}`);
      if (page.status !== 200) continue;
      const ext = [...page.body.matchAll(/<a\b[^>]*\bhref\s*=\s*["'](https?:\/\/[^"']+)["']/gi)].map((m) => m[1])
        .map((u) => { try { return new URL(u); } catch { return null; } })
        .filter((u) => u && !/(?:^|\.)(?:coingate\.com|gmpg\.org|w\.org|wordpress\.org)$/i.test(u.host) && !NOT_MERCHANT.test(u.host));
      const key = slug.replace(/-(?:com|net|org|io)$/, "").replace(/[^a-z0-9]/gi, "").toLowerCase();
      const best = ext.find((u) => u.host.replace(/[^a-z0-9]/gi, "").toLowerCase().includes(key)) ?? ext[0];
      const d = best ? norm(best.host) : "";
      // Many such stores show CoinGate only inside checkout, so the site check often finds nothing; the listing is the lead.
      if (d && !have.has(d) && !found.some((f) => f.domain === d)) found.push({ domain: d, name: c.name, source: "coingate-directory", gateway: "CoinGate (listed)" });
    } catch { /* skip */ }
  }
  console.error(`coingate: ${read} of ${last} category pages read, ${direct.length} Pay Direct stores, ${todo.length} not in merchants.csv, ${found.length} new domains`);
  return found;
}

// ---------- monthly re-check of published stores ----------
// The same checks on every "yes" store in merchants.csv. State lives in research/recheck.csv, one row per store:
//   seen     strongest sign the bot has ever found there (strong / weak); empty if it never found one
//   last_ok  last run that found a sign at least as strong as `seen`; the site's `checked` date follows it
//   misses   runs in a row since then that could read the site and did not find that sign
//   status   ok | review (hidden from the site until a person checks) | manual (the bot never saw a sign here,
//            e.g. crypto only inside checkout: not judged, not hidden, its date is not moved)
// blocked / error / robots runs change nothing: the bot could not look. A store that says it does not take crypto
// counts as a miss even if the bot never saw a sign. Two misses in a row => review. A review row stays until a
// person deletes it (the next run starts that store afresh) or marks the store "no" in merchants.csv.
const RECHECK = join(RESEARCH, "recheck.csv");
const RECHECK_COLS = ["domain", "name", "status", "misses", "seen", "last_ok", "last_run", "last_result", "signals", "evidence_url", "note"];
const LEVEL = { weak: 1, strong: 2 };

function recheckStep(prev, r, today) {
  const s = {
    status: prev?.status ?? "", misses: Number(prev?.misses) || 0, seen: prev?.seen ?? "", last_ok: prev?.last_ok ?? "",
    last_run: today, last_result: r.result, signals: r.signals, evidence_url: r.evidence_url, note: r.note,
  };
  const level = LEVEL[r.result] ?? 0;
  if (level && level >= (LEVEL[s.seen] ?? 0)) { s.seen = r.result; s.misses = 0; s.last_ok = today; }
  else if (level || r.result === "negative" || (r.result === "none" && s.seen)) s.misses++; // weaker sign than before counts too
  if (s.status !== "review") s.status = s.misses >= 2 ? "review" : s.seen ? "ok" : "manual";
  return s;
}

async function recheckPublished(limit) {
  const today = new Date().toLocaleDateString("sv-SE");
  const live = [...new Map(known().filter((m) => m.verified.trim() === "yes").map((m) => [m.domain.trim(), m])).values()];
  const prev = new Map((existsSync(RECHECK) ? parseCsv(readFileSync(RECHECK, "utf8")) : []).map((r) => [r.domain, r]));
  const results = await pool(live.slice(0, limit), PARALLEL_SITES, async (m) => ({ m, r: await checkSite(norm(m.domain)) }));
  const fresh = new Map(results.map(({ m, r }) => {
    const d = m.domain.trim();
    return [d, { domain: d, name: m.name, ...recheckStep(prev.get(d), r, today) }];
  }));
  // Stores left out by --limit keep their row; stores no longer "yes" drop out. Review rows go first.
  const rows = live.map((m) => fresh.get(m.domain.trim()) ?? prev.get(m.domain.trim())).filter(Boolean)
    .sort((a, b) => Number(b.status === "review") - Number(a.status === "review"));
  writeFileSync(RECHECK, toCsv(rows, RECHECK_COLS));

  const tally = {}; for (const { r } of results) tally[r.result] = (tally[r.result] ?? 0) + 1;
  const by = (st) => rows.filter((r) => r.status === st);
  console.log(`recheck ${today}: checked ${results.length}`, tally);
  console.log(`${rows.length} published stores: ok ${by("ok").length}, manual ${by("manual").length}, review ${by("review").length} -> ${RECHECK}`);
  for (const r of by("review")) console.log(`  hidden until a person checks: ${r.domain} (last sign ${r.last_ok || "never"}, now ${r.last_result})`);
  for (const r of rows.filter((r) => r.status !== "review" && Number(r.misses) === 1)) console.log(`  one miss, next run decides: ${r.domain} (${r.last_result})`);
}

// ---------- main ----------
const args = process.argv.slice(2);
const opt = (k) => { const i = args.indexOf(k); return i >= 0 ? args.splice(i, 2)[1] : undefined; };
const limit = Number(opt("--limit") ?? Infinity);
const outPath = opt("--out") ?? join(RESEARCH, "candidates.csv");
const [mode = "known", ...rest] = args;

if (mode === "recheck") { await recheckPublished(limit); process.exit(0); }

let targets;
if (mode === "known") targets = known().map((m) => ({ domain: norm(m.domain), name: m.name, source: "merchants.csv", verified: m.verified, gateway: m.gateway, kind: m.kind }));
else if (mode === "bitpay") targets = await bitpayCandidates();
else if (mode === "coingate") targets = await coingateCandidates(limit);
else if (mode === "domain") targets = rest.map((d) => ({ domain: norm(d), name: "", source: "manual" }));
else { console.error("mode: known | bitpay | coingate | domain <d...> | recheck"); process.exit(1); }
targets = targets.filter((t) => t.domain).slice(0, limit);

const checkedAt = new Date().toLocaleDateString("sv-SE"); // local YYYY-MM-DD
const results = await pool(targets, PARALLEL_SITES, async (t) => ({ ...t, ...(await checkSite(t.domain)), checked_at: checkedAt }));

const cols = ["domain", "name", "source", "result", "signals", "evidence_url", "http", "pages", "note", "checked_at", "verified", "gateway", "kind"];
// Keep earlier candidates for other domains; replace rows for domains checked now.
let prev = existsSync(outPath) ? parseCsv(readFileSync(outPath, "utf8")) : [];
const now = new Set(results.map((r) => r.domain));
prev = prev.filter((r) => !now.has(r.domain));
writeFileSync(outPath, toCsv([...prev, ...results], cols));

const tally = {}; for (const r of results) tally[r.result] = (tally[r.result] ?? 0) + 1;
console.log(`checked ${results.length}:`, tally, `-> ${outPath}`);
