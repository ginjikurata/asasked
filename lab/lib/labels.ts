// Pure helpers safe for client components (no fs).
import type { Merchant } from "./merchants";

export const slug = (s: string) => s.replace(/&/g, "and").replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "").toLowerCase();

// Readable names for merchant.group.
export const GROUP_LABEL: Record<string, string> = {
  "jewelry & watches": "Jewelry & watches",
  travel: "Travel & private jets",
  electronics: "Electronics",
  "software & web": "Software & web",
  "precious metals": "Gold & silver",
  "games & entertainment": "Games & fun",
  "fashion & beauty": "Fashion & beauty",
  "gift cards": "Gift cards",
  "home & garden": "Home & garden",
  "sports & outdoors": "Sports & outdoors",
  "cars & boats": "Cars & boats",
  "food & drink": "Food & drink",
  other: "Other",
};

export const gatewayName = (g: string) => (g === "own" ? "Own checkout" : g === "unknown" ? "Not named" : g);

export function pays(m: Merchant) {
  const via = m.gateway === "own" ? "own checkout" : m.gateway === "unknown" ? "" : m.gateway;
  return [m.payment === "crypto" ? "Crypto" : m.payment, via && `via ${via}`].filter(Boolean).join(" ");
}

// The research file's short network codes, in words a shopper understands.
export function networkName(n: string) {
  const t = n.trim();
  if (!t) return "";
  if (t === "multi") return "Several coins and networks";
  if (t === "Base") return "USDC on Base";
  if (t === "Base+") return "USDC on Base and other networks";
  if (t === "Solana") return "Solana (SOL, USDC)";
  if (t === "Solana+") return "Solana and other networks";
  if (t === "USDC Ethereum only") return "USDC on Ethereum only";
  return t;
}

// Evidence notes are written for us ("pi-usdc icon (browser check)"); rewrite the jargon for shoppers.
export function evidenceNote(note: string) {
  return note
    .replace(/\s*\(browser check\)/gi, "")
    // pi-usdc is the USDC logo in a Shopify store's payment icons; say where it was seen, nothing more.
    .replace(/pi-usdc icon on (the )?homepage/gi, "USDC logo among the payment icons on the store's homepage")
    .replace(/pi-usdc icon/gi, "USDC logo among the store's payment icons")
    .replace(/\+ UCP catalog/gi, "and a public product list")
    .replace(/UCP catalog/gi, "public product list")
    .replace(/listed in BitPay directory \(direct pay\)/gi, "listed in BitPay's store directory")
    .replace(/\s+/g, " ")
    .trim();
}

// Evidence that is only an old news item or blog post, not the store's payment page or checkout.
export const weakEvidence = (note: string, url: string | null) =>
  /news|blog|press|announce|\b20(1\d|2[0-3])\b/i.test(`${note} ${url ?? ""}`);

export function fmtDate(d: string | null) {
  if (!d) return null;
  return new Date(`${d}T12:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}
