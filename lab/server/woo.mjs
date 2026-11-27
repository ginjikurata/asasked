// Bottega Senatore through the WooCommerce Store API: plain HTTP requests, no hidden browser,
// nothing bypassed. A cart lives at the store under a cart token; we keep only that token.
// The delivery address passes through place() in memory and is never written anywhere here.
//   LAB_WOO_BASE  Store API root (default Bottega Senatore); tests point it at a local stub.
import { BITPAY } from "./invoice.mjs";

export const STORE = { domain: "bottegasenatore.com", name: "Bottega Senatore", payment: "bitpay_checkout_gateway" };
const BASE = (process.env.LAB_WOO_BASE ?? "https://bottegasenatore.com/wp-json/wc/store/v1").replace(/\/+$/, "");
const UA = "AsAskedLabBot/0.1 (+https://lab.asasked.dev; finds stores that accept crypto)";

export class StoreError extends Error {
  constructor(message, code) {
    super(message);
    this.code = code;
  }
}
const plain = (s) => String(s ?? "").replace(/<[^>]*>/g, "").replace(/&[a-z#0-9]+;/gi, " ").replace(/\s+/g, " ").trim().slice(0, 300);

// One cart session at the store.
class Cart {
  constructor(token = "", nonce = "") {
    this.token = token;
    this.nonce = nonce;
  }
  async call(method, path, body) {
    let r;
    try {
      r = await fetch(BASE + path, {
        method,
        redirect: "error",
        signal: AbortSignal.timeout(20_000),
        headers: {
          "user-agent": UA,
          accept: "application/json",
          ...(body ? { "content-type": "application/json" } : {}),
          ...(this.token ? { "cart-token": this.token } : {}),
          ...(this.nonce ? { nonce: this.nonce } : {}),
        },
        body: body ? JSON.stringify(body) : undefined,
      });
    } catch (e) {
      throw new StoreError(`The store did not answer (${e.name === "TimeoutError" ? "timeout" : "network"}).`, "network");
    }
    this.token = r.headers.get("cart-token") || this.token;
    this.nonce = r.headers.get("nonce") || this.nonce;
    let j = null;
    try {
      j = await r.json();
    } catch {}
    if (!r.ok) throw new StoreError(plain(j?.message) || `The store answered ${r.status}.`, j?.code ?? String(r.status));
    return j;
  }
}

const money = (minor, unit) => Number(minor) / 10 ** Number(unit ?? 2);

// What we keep and show about a store cart. No address parts in here.
function snapshot(c) {
  const t = c.totals ?? {};
  const unit = t.currency_minor_unit ?? 2;
  const pkg = c.shipping_rates?.[0];
  const rate = pkg?.shipping_rates?.find((r) => r.selected);
  return {
    items: (c.items ?? []).map((i) => ({
      key: i.key,
      id: i.id,
      name: plain(i.name),
      option: (i.variation ?? []).map((v) => plain(v.value)).join(" / "),
      quantity: i.quantity,
      price: money(i.prices?.price, i.prices?.currency_minor_unit ?? unit),
      total: money(i.totals?.line_total, unit),
    })),
    currency: t.currency_code ?? "",
    subtotal: money(t.total_items, unit),
    shipping: money(t.total_shipping ?? 0, unit),
    tax: money(t.total_tax ?? 0, unit),
    total: money(t.total_price, unit),
    total_minor: String(t.total_price ?? ""),
    shipping_name: rate ? plain(rate.name) : null,
    needs_shipping: !!c.needs_shipping,
    payment_ok: (c.payment_methods ?? []).includes(STORE.payment),
    errors: (c.errors ?? []).map((e) => plain(e.message)),
  };
}

// Region only: enough for the store to price shipping and tax.
const region = (r) => ({ country: String(r.country ?? "").toUpperCase().slice(0, 2), state: String(r.state ?? "").slice(0, 40), postcode: String(r.postcode ?? "").slice(0, 20) });

async function cheapestShipping(cart, c) {
  const pkg = c.shipping_rates?.[0];
  const rates = pkg?.shipping_rates ?? [];
  if (!rates.length) return c;
  const best = [...rates].sort((a, b) => Number(a.price) - Number(b.price))[0];
  if (best.selected) return c;
  return cart.call("POST", "/cart/select-shipping-rate", { package_id: pkg.package_id ?? 0, rate_id: best.rate_id });
}

// A fresh store cart with these items, shipping priced for the region. Creates no order.
// items: [{id, quantity}] where id is the Woo product or variation id.
export async function prepare(items, where) {
  const cart = new Cart();
  let c = await cart.call("GET", "/cart");
  for (const it of items) c = await cart.call("POST", "/cart/add-item", { id: it.id, quantity: it.quantity });
  const r = region(where);
  if (r.country) c = await cart.call("POST", "/cart/update-customer", { shipping_address: r, billing_address: r });
  c = await cheapestShipping(cart, c);
  return { token: cart.token, nonce: cart.nonce, snap: snapshot(c) };
}

// Store address fields from our Address {name, line1, line2, city, region, postal, country, phone, email}.
function storeAddress(a) {
  const name = String(a.name ?? "").trim();
  const cut = name.lastIndexOf(" ");
  const base = {
    first_name: cut > 0 ? name.slice(0, cut) : name,
    last_name: cut > 0 ? name.slice(cut + 1) : name,
    address_1: String(a.line1 ?? ""),
    address_2: String(a.line2 ?? ""),
    city: String(a.city ?? ""),
    state: String(a.region ?? ""),
    postcode: String(a.postal ?? ""),
    country: String(a.country ?? "").toUpperCase(),
    phone: String(a.phone ?? ""),
  };
  return { shipping: base, billing: { ...base, email: String(a.email ?? "") } };
}

// Put the full address on the store cart and read the total again. Still no order.
export async function reprice(token, nonce, address) {
  const cart = new Cart(token, nonce);
  const { shipping, billing } = storeAddress(address);
  let c = await cart.call("POST", "/cart/update-customer", { shipping_address: shipping, billing_address: billing });
  c = await cheapestShipping(cart, c);
  return { token: cart.token, nonce: cart.nonce, snap: snapshot(c) };
}

// Creates the order (unpaid) for exactly expected_total, then opens the order-received link once:
// that is when the store makes the BitPay invoice and redirects to it. Returns the invoice link.
export async function place(token, nonce, address, expectedMinor) {
  const cart = new Cart(token, nonce);
  const { shipping, billing } = storeAddress(address);
  const o = await cart.call("POST", "/checkout", {
    billing_address: billing,
    shipping_address: shipping,
    payment_method: STORE.payment,
    expected_total: String(expectedMinor),
  });
  const order = { id: o?.order_id ?? null, status: o?.status ?? null };
  const next = o?.payment_result?.redirect_url;
  if (!next) return { order, invoice: null, note: "The store made the order but gave no payment link." };
  let link;
  try {
    link = new URL(next, BASE);
  } catch {
    return { order, invoice: null, note: "The store's payment link is broken." };
  }
  if (link.protocol !== "https:" && !link.host.startsWith("127.0.0.1")) return { order, invoice: null, note: "The store's payment link is not https." };
  if (link.href.startsWith(BITPAY + "/i/")) return { order, invoice: link.href };
  let r;
  try {
    r = await fetch(link, { redirect: "manual", signal: AbortSignal.timeout(20_000), headers: { "user-agent": UA, ...(token ? { "cart-token": cart.token } : {}) } });
  } catch {
    return { order, invoice: null, note: "The store did not answer when asked for the invoice." };
  }
  const loc = r.headers.get("location");
  const inv = loc ? new URL(loc, link).href : "";
  return inv.startsWith(BITPAY + "/i/") ? { order, invoice: inv } : { order, invoice: null, note: "The store did not send a BitPay invoice." };
}

// Take the street, name and contacts off a store cart again: only the region stays (best effort).
export async function forget(token, nonce, where) {
  const cart = new Cart(token, nonce);
  if (token) {
    try {
      const r = region(where ?? {});
      await cart.call("POST", "/cart/update-customer", { shipping_address: { ...BLANK, ...r }, billing_address: { ...BLANK, ...r, email: "" } });
    } catch {}
  }
  return { token: cart.token, nonce: cart.nonce };
}
const BLANK = { first_name: "", last_name: "", address_1: "", address_2: "", city: "", phone: "" };

// Empty a store cart we no longer need (best effort).
export async function clear(token, nonce) {
  if (!token) return;
  const cart = new Cart(token, nonce);
  try {
    const c = await cart.call("GET", "/cart");
    for (const i of c.items ?? []) await cart.call("POST", "/cart/remove-item", { key: i.key });
  } catch {}
}
