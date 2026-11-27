// Orders at Bottega Senatore through the server. Two steps, and only the second makes an order:
//   prepareOrder  builds a store cart, prices shipping for a region and runs the guard. No order.
//                 Agents (MCP, scope save_cart) and the person on the page can both do this.
//   placeOrder    only the person on the page: the unlocked address comes in that one request, goes
//                 to the store and is never written anywhere. Then the BitPay invoice is checked.
// Paying is always the person's own wallet. We never hold money or keys.
import { check, product, productOut } from "./catalog.mjs";
import { checkInvoice, verdict } from "./invoice.mjs";
import * as S from "./store.mjs";
import * as woo from "./woo.mjs";

export class OrderError extends Error {
  constructor(message, status = 400, order = null) {
    super(message);
    this.status = status;
    this.order = order;
  }
}
const text = (v, max) => (typeof v === "string" ? v.trim().slice(0, max) : "");
const near = (a, b) => Math.abs(Number(a) - Number(b)) < 0.005;

// Catalog items -> what we order. Only Bottega Senatore, only options that are in stock.
export function resolveItems(request, list) {
  if (!Array.isArray(list) || !list.length) throw new OrderError("items is empty.");
  if (list.length > 10) throw new OrderError("At most 10 items.");
  return list.map((it) => {
    const p = product(text(it?.url, 500));
    if (!p) throw new OrderError(`No product with url ${text(it?.url, 200)} in the catalog.`);
    const out = productOut(p);
    if (out.store_domain !== woo.STORE.domain) throw new OrderError(`Orders work only at ${woo.STORE.name} for now. "${p.t}" is at ${out.store}: buy it on the store's site.`);
    const option = text(it?.option, 60) || null;
    const opt = option ? (p.v ?? []).find(([, l]) => l.toLowerCase() === option.toLowerCase()) : null;
    if ((p.v ?? []).length && !opt) throw new OrderError(`Pick one of the options for "${p.t}": ${(p.v ?? []).map((o) => o[1]).join(", ")}.`);
    if (opt && opt[3] === false) throw new OrderError(`Option ${opt[1]} of "${p.t}" is sold out.`);
    if (!opt && p.a === false) throw new OrderError(`"${p.t}" is sold out.`);
    const c = check(p, request, opt ? opt[1] : undefined);
    return {
      url: p.u,
      title: p.t,
      store: out.store,
      option: opt ? opt[1] : null,
      option_id: opt ? opt[0] : null,
      woo_id: opt ? opt[0] : p.i,
      price: opt && typeof opt[2] === "number" ? opt[2] : p.p,
      currency: p.c,
      quantity: Math.min(10, Math.max(1, Number.parseInt(it?.quantity, 10) || 1)),
      check: { fits: c.fits, good: c.good, bad: c.bad },
    };
  });
}

// Region for shipping only: country, state, postcode. Never a street or a name.
export function cleanRegion(r) {
  if (!r || typeof r !== "object") return {};
  const country = text(r.country, 2).toUpperCase();
  return /^[A-Z]{2}$/.test(country) ? { country, state: text(r.state, 40), postcode: text(r.postcode, 20) } : {};
}

// The guard lines for a store cart against what was asked.
function fitLines(items, snap) {
  const lines = [];
  for (const i of items) {
    const name = i.option ? `${i.title} (${i.option})` : i.title;
    lines.push(i.check.fits ? { ok: true, text: `${name} fits the request` } : { ok: false, text: `${name}: ${i.check.bad.join("; ")}` });
  }
  const want = new Map(items.map((i) => [Number(i.woo_id), i]));
  const got = new Map((snap.items ?? []).map((i) => [Number(i.id), i]));
  const same = want.size === got.size && [...want].every(([id, i]) => got.get(id)?.quantity === i.quantity);
  lines.push(same ? { ok: true, text: "The store cart has exactly these items and quantities" } : { ok: false, text: "The store cart does not match the items asked for." });
  for (const [id, i] of want) {
    const s = got.get(id);
    if (s && typeof i.price === "number" && !near(s.price, i.price))
      lines.push({ ok: null, text: `${i.title}: the store price is ${s.price} ${snap.currency}, the catalog said ${i.price}. The store price is what you pay.` });
  }
  if (items.some((i) => i.currency && snap.currency && i.currency !== snap.currency)) lines.push({ ok: null, text: `The store prices this cart in ${snap.currency}.` });
  lines.push(snap.payment_ok ? { ok: true, text: "The store offers BitPay for this cart" } : { ok: false, text: "The store does not offer BitPay for this cart." });
  for (const e of snap.errors ?? []) lines.push({ ok: false, text: `Store: ${e}` });
  if (snap.needs_shipping && !snap.shipping_name) lines.push({ ok: null, text: "No shipping price yet. It shows after the address goes in." });
  return lines;
}

const fitOf = (items, snap) => {
  const lines = fitLines(items, snap);
  return { lines, verdict: verdict(lines) };
};

// args: {request, items | cart_id, where:{country,state,postcode}, agent: name or null}
export async function prepareOrder(address, args) {
  const request = text(args.request, 300);
  let list = args.items;
  if (args.cart_id) {
    const cart = S.listCarts(address).find((c) => c.id === args.cart_id);
    if (!cart) throw new OrderError("No such saved cart.", 404);
    list = cart.items.map((i) => ({ url: i.url, option: i.option, quantity: i.quantity }));
    if (!request) args = { ...args, request: cart.request };
  }
  const req = text(args.request, 300);
  if (!req) throw new OrderError("request is empty.");
  const items = resolveItems(req, list);
  const where = cleanRegion(args.where);
  let cart;
  try {
    cart = await woo.prepare(items.map((i) => ({ id: i.woo_id, quantity: i.quantity })), where);
  } catch (e) {
    if (e instanceof woo.StoreError) throw new OrderError(`The store did not take this cart: ${e.message}`, 502);
    throw e;
  }
  const fit = fitOf(items, cart.snap);
  const order = S.addOrder(address, { agent: args.agent ?? null, request: req, items, fit, country: where.country ?? null, token: cart.token, nonce: cart.nonce, snap: cart.snap });
  for (const t of S.pruneOrders(address)) await woo.clear(t.token, t.nonce);
  return order;
}

// The unlocked address, checked and cut to size. Lives only in this request.
export function cleanAddress(a) {
  if (!a || typeof a !== "object") throw new OrderError("address is missing.");
  const f = (k, max) => text(a[k], max);
  const out = {
    name: f("name", 100), line1: f("line1", 200), line2: f("line2", 200), city: f("city", 100), region: f("region", 100),
    postal: f("postal", 20), country: f("country", 2).toUpperCase(), phone: f("phone", 40), email: f("email", 200),
  };
  for (const k of ["name", "line1", "city", "postal", "country", "email"]) if (!out[k]) throw new OrderError(`The address needs ${k}.`);
  if (!/^[A-Z]{2}$/.test(out.country)) throw new OrderError("country must be a 2-letter code, like US or DE.");
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(out.email)) throw new OrderError("The email does not look right.");
  return out;
}

// Only the person on the page. Places the order only if the total is the one they saw.
export async function placeOrder(address, orderId, rawAddress, totalMinor) {
  const addr = cleanAddress(rawAddress);
  const o = S.takeForPlacing(address, orderId);
  if (!o) throw new OrderError("This order cannot be placed now. It may be placed already, expired or in progress.", 409, S.getOrder(address, orderId));
  const back = async (token, nonce, snap, fit, msg) => {
    const f = await woo.forget(token, nonce, { country: o.country });
    S.backToPrepared(o.id, f.token, f.nonce, snap ?? o.snap, fit);
    throw new OrderError(msg, 409, S.getOrder(address, o.id));
  };
  if (o.fit?.verdict === "stop") await back(o.token, o.nonce, null, null, "The guard said stop for this cart. It cannot be ordered.");
  if (String(totalMinor) !== String(o.snap.total_minor)) await back(o.token, o.nonce, null, null, "The total you confirmed is not the current total. Look again.");

  // The full address goes on the store cart: shipping and tax can change.
  let r;
  try {
    r = await woo.reprice(o.token, o.nonce, addr);
  } catch (e) {
    if (!(e instanceof woo.StoreError)) throw e;
    await back(o.token, o.nonce, null, null, `The store did not take the address: ${e.message}`);
  }
  const fit = fitOf(o.items, r.snap);
  if (fit.verdict === "stop") await back(r.token, r.nonce, r.snap, fit, "With your address the guard says stop. Nothing was ordered.");
  if (r.snap.total_minor !== o.snap.total_minor)
    await back(r.token, r.nonce, r.snap, fit, `With your address the total is ${r.snap.total} ${r.snap.currency} (was ${o.snap.total}). Nothing was ordered. Confirm the new total to go on.`);

  // From here an order exists at the store (unpaid).
  let placed;
  try {
    placed = await woo.place(r.token, r.nonce, addr, r.snap.total_minor);
  } catch (e) {
    await woo.forget(r.token, r.nonce, { country: o.country });
    await woo.clear(r.token, r.nonce);
    const note = e instanceof woo.StoreError ? `The store did not make the order: ${e.message}` : "Something went wrong while ordering.";
    S.finishOrder(o.id, { status: "failed", note, snap: r.snap });
    if (!(e instanceof woo.StoreError)) console.error("place", e);
    return S.getOrder(address, o.id);
  }
  await woo.forget(r.token, r.nonce, { country: o.country });
  const orderNo = placed.order.id != null ? String(placed.order.id) : null;
  if (!placed.invoice) {
    S.finishOrder(o.id, { status: "placed", order_id: orderNo, note: `${placed.note ?? "No invoice."} Do not pay anywhere else. The store will email you.`, snap: r.snap });
    return S.getOrder(address, o.id);
  }
  const inv = await checkInvoice(placed.invoice, { total: r.snap.total, currency: r.snap.currency, merchant: woo.STORE.name });
  S.finishOrder(o.id, {
    status: "placed",
    order_id: orderNo,
    invoice_url: inv.invoice_url,
    invoice: { lines: inv.lines, verdict: inv.verdict, pay: inv.pay, usdc: inv.usdc },
    note: inv.verdict === "stop" ? "The guard said stop for this invoice. Do not pay it. Unpaid, the order does nothing; the store may cancel it." : null,
    snap: r.snap,
  });
  return S.getOrder(address, o.id);
}

// Cancel a prepared order (no store order exists yet) and empty its store cart.
export async function cancelOrder(address, orderId) {
  const t = S.cancelOrder(address, orderId);
  if (!t) return false;
  await woo.clear(t.token, t.nonce);
  return true;
}

// Timer: prepared orders past their time lose the cart token; empty those store carts.
export async function sweepOrders() {
  for (const t of S.expireOrders()) await woo.clear(t.token, t.nonce);
}
