// Build-time view of the catalog for server components: stores grouped by category,
// plus the product list read from public/products.json.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { MERCHANTS, type Merchant } from "./merchants";
import type { Data } from "./products";
import { GROUP_LABEL, slug } from "./labels";

export { GROUP_LABEL, evidenceNote, fmtDate, gatewayName, networkName, pays, slug, weakEvidence } from "./labels";

export function loadProducts(): Data {
  return JSON.parse(readFileSync(join(process.cwd(), "public/products.json"), "utf8"));
}

export type Group = { key: string; slug: string; label: string; stores: Merchant[] };

export function groups(): Group[] {
  const by = new Map<string, Merchant[]>();
  for (const m of MERCHANTS) by.set(m.group, [...(by.get(m.group) ?? []), m]);
  return [...by]
    .map(([key, stores]) => ({ key, slug: slug(key), label: GROUP_LABEL[key] ?? key, stores: stores.sort((a, b) => a.name.localeCompare(b.name)) }))
    .sort((a, b) => (a.key === "other" ? 1 : b.key === "other" ? -1 : b.stores.length - a.stores.length || a.label.localeCompare(b.label)));
}
