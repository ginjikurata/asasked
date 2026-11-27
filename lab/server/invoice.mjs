// The guard on a BitPay invoice, run on our server. Same checks as the browser extension:
// the pure rules live in ../extension/guard.js and are loaded from there, so both stay the same.
// Reads the invoice through BitPay's public JSON Payment Protocol (v2). Pays nothing.
//   LAB_BITPAY_BASE  BitPay origin (default https://bitpay.com); tests point it at a local stub.
import { createRequire } from "node:module";

const G = createRequire(import.meta.url)("../extension/guard.js");
export const BITPAY = (process.env.LAB_BITPAY_BASE ?? "https://bitpay.com").replace(/\/+$/, "");
const UA = "AsAskedLabBot/0.1 (+https://lab.asasked.dev; finds stores that accept crypto)";
const H = { "X-Paypro-Version": "2", "user-agent": UA };
export const verdict = G.verdict;

// Only an invoice page on BitPay itself: https://bitpay.com/i/<id>.
export function invoiceUrl(u) {
  let url;
  try {
    url = new URL(u, BITPAY);
  } catch {
    return null;
  }
  const m = url.pathname.match(/^\/i\/([A-Za-z0-9]{10,40})$/);
  return url.origin === new URL(BITPAY).origin && m ? `${BITPAY}/i/${m[1]}` : null;
}

async function getJSON(u, init = {}) {
  const r = await fetch(u, { ...init, redirect: "error", signal: AbortSignal.timeout(15_000) });
  if (!r.ok) throw new Error(`${r.status} ${(await r.text().catch(() => "")).slice(0, 120)}`.trim());
  return r.json();
}

// How many USD one unit of `cur` is, from BitPay's public rates (both quoted against BTC).
async function usdPer(cur) {
  if (!cur || cur === "USD") return 1;
  if (!/^[A-Z]{3}$/.test(cur)) return NaN;
  try {
    const [usd, other] = await Promise.all([getJSON(`${BITPAY}/rates/BTC/USD`, { headers: H }), getJSON(`${BITPAY}/rates/BTC/${cur}`, { headers: H })]);
    return usd.data.rate / other.data.rate;
  } catch {
    return NaN;
  }
}

// snap: {total, currency, merchant} — the order total in major units (483.00), as the store confirmed it.
// Returns the guard lines, the verdict and what the wallet will be asked to send.
export async function checkInvoice(u, snap) {
  const url = invoiceUrl(u);
  if (!url) return { lines: [{ ok: false, text: "The store did not send a BitPay invoice link." }], verdict: "stop", invoice_url: null };
  let lines = [];
  let option = null;
  let usdc;
  try {
    const opts = await getJSON(url, { headers: { ...H, Accept: "application/payment-options" } });
    const first = G.options(opts, snap, await usdPer(snap.currency));
    lines = first.lines;
    option = first.option;
    usdc = first.usdc;
  } catch (e) {
    lines.push({ ok: null, text: `Could not read the invoice (${e.message}). Check the amount and merchant on the BitPay page yourself.` });
  }
  let pay = null;
  if (option) {
    try {
      const req = await getJSON(url, {
        method: "POST",
        headers: { ...H, "Content-Type": "application/payment-request" },
        body: JSON.stringify({ chain: "SOL", currency: "USDC" }),
      });
      lines = lines.concat(G.request(req, option));
      const out = (req.instructions ?? []).flatMap((i) => i.outputs ?? [])[0];
      if (out) pay = { address: String(out.address), usdc: Number(out.amount) / 10 ** Number(option.decimals || 6) };
    } catch (e) {
      lines.push({ ok: null, text: `Could not get the payment details (${e.message}).` });
    }
  }
  return { lines, verdict: G.verdict(lines), invoice_url: url, usdc: usdc ?? null, pay };
}
