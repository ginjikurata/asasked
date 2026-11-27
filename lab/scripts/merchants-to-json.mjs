// Converts ../research/merchants.csv into lib/merchants.json for the catalog page.
// Only stores whose payment we confirmed on their own site (yes) are published;
// "partial" and "no" rows stay in the research file and never reach the site.
// On a host without the research folder, the committed lib/merchants.json is kept as is.
// research/recheck.csv (written by `node scripts/discover.mjs recheck`), when present: stores in status "review"
// are left out until a person checks them, and `checked` moves to the last re-check that found the sign (last_ok).
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const src = process.env.MERCHANTS_CSV ?? join(here, "../../research/merchants.csv");
const out = join(here, "../lib/merchants.json");
if (!existsSync(src)) {
  if (!existsSync(out)) { console.error(`no ${src} and no lib/merchants.json`); process.exit(1); }
  console.log("no merchants.csv found, keeping existing lib/merchants.json");
  process.exit(0);
}

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
  return rows.filter((r) => r.some((v) => v.trim()));
}

// The research file uses fine-grained categories; the filter shows broad groups.
// Unknown categories fall into "other" and are listed on the build output so they get a group.
const GROUPS = {
  "jewelry & watches": ["jewelry", "diamonds", "watches", "watches/jewelry", "luxury gifts"],
  "fashion & beauty": ["fashion", "clothing", "clothing (uk)", "kids clothing", "beauty", "merch"],
  electronics: ["electronics", "electronics/luxury", "consoles/phones", "phones", "photo gear", "dj equipment", "hardware wallets"],
  travel: ["travel", "private aviation"],
  "cars & boats": ["cars", "yachts"],
  "precious metals": ["precious metals", "precious metals (us)", "precious metals (uk)"],
  "software & web": ["software", "hosting/domains", "freelance"],
  "games & entertainment": ["games", "trading cards", "tv/streaming", "sports tickets"],
  "gift cards": ["gift cards"],
  "home & garden": ["furniture", "hydroponics", "fertilizers", "pet supplies"],
  "sports & outdoors": ["bicycles", "outdoor"],
  "food & drink": ["coffee", "wine", "food", "convenience"],
  other: ["shipping", "retail"],
};
const GROUP_OF = new Map(Object.entries(GROUPS).flatMap(([g, cats]) => cats.map((c) => [c, g])));
const ungrouped = new Set();
function groupOf(category) {
  const g = GROUP_OF.get(category.toLowerCase());
  if (!g && category) ungrouped.add(category);
  return g ?? "other";
}

const [head, ...body] = parseCsv(readFileSync(src, "utf8"));
const records = body.map((r) => Object.fromEntries(head.map((k, i) => [k, (r[i] ?? "").trim()])));

const recheckSrc = process.env.RECHECK_CSV ?? join(dirname(src), "recheck.csv");
const recheck = new Map();
if (existsSync(recheckSrc)) {
  const [rh, ...rb] = parseCsv(readFileSync(recheckSrc, "utf8"));
  for (const r of rb) { const o = Object.fromEntries(rh.map((k, i) => [k, (r[i] ?? "").trim()])); recheck.set(o.domain, o); }
}
const hidden = [];

const merchants = records
  .filter((r) => r.verified === "yes")
  .filter((r) => {
    if (recheck.get(r.domain)?.status !== "review") return true;
    hidden.push(r.domain);
    return false;
  })
  .map((r) => {
    const own = r.verified_how.match(/\d{4}-\d{2}-\d{2}/)?.[0] ?? null;
    const ok = recheck.get(r.domain)?.last_ok || null;
    const date = own && ok ? (ok > own ? ok : own) : own ?? ok;
    return {
      name: r.name,
      domain: r.domain,
      url: `https://${r.domain}`,
      category: r.category || "other",
      group: groupOf(r.category),
      kind: r.kind || "online",
      payment: r.payment || "crypto",
      gateway: r.gateway || "unknown",
      network: r.network || "",
      status: r.verified,
      checked: date,
      how: r.verified_how.replace(/\s*\d{4}-\d{2}-\d{2}\s*$/, ""),
    };
  })
  .sort((a, b) => (a.status === b.status ? a.name.localeCompare(b.name) : a.status === "yes" ? -1 : 1));

writeFileSync(out, JSON.stringify(merchants, null, 2) + "\n");
if (ungrouped.size) console.warn(`no group for: ${[...ungrouped].join(", ")} (shown as "other")`);
if (hidden.length) console.warn(`hidden until a person checks (recheck.csv status review): ${hidden.join(", ")}`);
console.log(`merchants.json: ${merchants.length} of ${records.length} rows published`);
